"""
IDL Ref:
    https://thrift.apache.org/docs/idl
"""

import collections
import itertools
import os
import threading
import types
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from ply import lex, yacc

from ..thrift import TException, TPayload, TPayloadMeta, TType, gen_init
from .exc import ThriftGrammarError, ThriftParserError
from .lexer import *  # noqa


def _annotations_to_dict(annotations):
    return {} if annotations is None else dict(annotations)


class _GrammarError(ThriftGrammarError):
    """Raised by ``p_error``, where PLY passes only a bare token (or None at
    EOF) without a way to reach the parser and its context; `_parse_data`
    catches it to add the file name to the message."""

    def __init__(self, value=None, lineno=None):
        super(_GrammarError, self).__init__()
        self.value = value
        self.lineno = lineno


def p_error(p):
    if p is None:
        raise _GrammarError()
    raise _GrammarError(p.value, p.lineno)


def p_start(p):
    '''start : header definition'''


def p_header(p):
    '''header : header_unit_ header
              |'''


def p_header_unit_(p):
    '''header_unit_ : header_unit ';'
                    | header_unit'''


def p_header_unit(p):
    '''header_unit : include
                   | cpp_include
                   | namespace'''


def p_include(p):
    '''include : INCLUDE LITERAL'''
    thrift = p.parser.context.thrift_stack[-1]
    if thrift.__thrift_file__ is None:
        raise ThriftParserError('Unexpected include statement while loading '
                                'from file like object.')
    replace_include_dirs = [os.path.dirname(thrift.__thrift_file__)] \
        + p.parser.context.include_dirs
    for include_dir in replace_include_dirs:
        path = os.path.join(include_dir, p[2])
        if os.path.exists(path):
            thrift_file_name_module = os.path.basename(thrift.__thrift_file__)
            if thrift_file_name_module.endswith(".thrift"):
                thrift_file_name_module = thrift_file_name_module[:-7] + "_thrift"
            module_prefix = str(thrift.__name__)[:-len(thrift_file_name_module)] if thrift.__name__.endswith(thrift_file_name_module) else ""

            child_rel_path = os.path.relpath(str(path), os.path.dirname(thrift.__thrift_file__))
            child_module_name = str(child_rel_path).replace(os.sep, ".")
            if child_module_name.endswith(".thrift"):
                child_module_name = child_module_name[:-7] + "_thrift"
            child_module_name = module_prefix + child_module_name

            child = parse(path, module_name=child_module_name,
                          _context=p.parser.context)
            child_include_module_name = os.path.basename(path)
            if child_include_module_name.endswith(".thrift"):
                child_include_module_name = child_include_module_name[:-7]
            setattr(child, '__name__', child_include_module_name)
            setattr(child, '__thrift_module_name__', child_module_name)
            setattr(thrift, child.__name__, child)
            _add_thrift_meta(thrift, 'includes', child)
            return
    raise ThriftParserError(('Couldn\'t include thrift %s in any '
                             'directories provided') % p[2])


def p_cpp_include(p):
    '''cpp_include : CPP_INCLUDE LITERAL'''


def p_namespace(p):
    '''namespace : NAMESPACE namespace_scope IDENTIFIER'''
    # namespace is useless in thriftpy2
    # if p[2] == 'py' or p[2] == '*':
    #     setattr(p.parser.context.thrift_stack[-1], '__name__', p[3])


def p_namespace_scope(p):
    '''namespace_scope : '*'
                       | IDENTIFIER'''
    p[0] = p[1]


def p_sep(p):
    '''sep : ','
           | ';'
    '''


def p_definition(p):
    '''definition : definition definition_unit_
                  |'''


def p_definition_unit_(p):
    '''definition_unit_ : definition_unit ';'
                        | definition_unit'''


def p_definition_unit(p):
    '''definition_unit : const
                       | ttype
    '''


def p_const(p):
    '''const : CONST field_type IDENTIFIER '=' const_value type_annotations
             | CONST field_type IDENTIFIER '=' const_value type_annotations sep'''
    _, field_type, name, _, const_value, annotations = p[1:7]
    try:
        val = _cast(field_type, p.lineno(3))(const_value)
    except AssertionError:
        raise ThriftParserError('Type error for constant %s at line %d' %
                                (name, p.lineno(3)))
    thrift = p.parser.context.thrift_stack[-1]
    setattr(thrift, name, val)
    _add_thrift_meta(thrift, 'consts', val)
    if annotations:
        if not hasattr(thrift, '__thrift_const_annotations__'):
            thrift.__thrift_const_annotations__ = {}
        thrift.__thrift_const_annotations__[name] = _annotations_to_dict(annotations)


def p_const_value(p):
    '''const_value : INTCONSTANT
                   | DUBCONSTANT
                   | LITERAL
                   | BOOLCONSTANT
                   | const_list
                   | const_map
                   | const_ref'''
    p[0] = p[1]


def p_const_list(p):
    '''const_list : '[' const_list_seq ']' '''
    p[0] = p[2]


def p_const_list_seq(p):
    '''const_list_seq : const_value sep const_list_seq
                      | const_value const_list_seq
                      |'''
    _parse_seq(p)


def p_const_map(p):
    '''const_map : '{' const_map_seq '}' '''
    p[0] = dict(p[2])


def p_const_map_seq(p):
    '''const_map_seq : const_map_item sep const_map_seq
                     | const_map_item const_map_seq
                     |'''
    _parse_seq(p)


def p_const_map_item(p):
    '''const_map_item : const_value ':' const_value '''
    p[0] = [p[1], p[3]]


def p_const_ref(p):
    '''const_ref : IDENTIFIER'''
    child = father = p.parser.context.thrift_stack[-1]
    for name in p[1].split('.'):
        father = child
        child = getattr(child, name, None)
        if child is None:
            raise ThriftParserError('Can\'t find name %r at line %d'
                                    % (p[1], p.lineno(1)))

    if _get_ttype(child) is None or _get_ttype(father) == TType.I32:
        # child is a constant or enum value
        p[0] = child
    else:
        raise ThriftParserError('No enum value or constant found '
                                'named %r' % p[1])


def p_ttype(p):
    '''ttype : typedef
             | enum
             | struct
             | union
             | exception
             | service'''


def p_typedef(p):
    '''typedef : TYPEDEF field_type IDENTIFIER type_annotations'''
    _, field_type, name, annotations = p[1:5]
    thrift = p.parser.context.thrift_stack[-1]
    setattr(thrift, name, field_type)
    if annotations:
        if not hasattr(thrift, '__thrift_typedef_annotations__'):
            thrift.__thrift_typedef_annotations__ = {}
        thrift.__thrift_typedef_annotations__[name] = _annotations_to_dict(annotations)


def p_enum(p):  # noqa
    '''enum : ENUM IDENTIFIER '{' enum_seq '}' type_annotations'''
    _, name, _, items, _, annotations = p[1:7]
    thrift = p.parser.context.thrift_stack[-1]
    val = _make_enum(thrift, name, items, annotations, lineno=p.lineno(2))
    setattr(thrift, name, val)
    _add_thrift_meta(thrift, 'enums', val)


def p_enum_seq(p):
    '''enum_seq : enum_item sep enum_seq
                | enum_item enum_seq
                |'''
    _parse_seq(p)


def p_enum_item(p):
    '''enum_item : IDENTIFIER '=' INTCONSTANT type_annotations
                 | IDENTIFIER type_annotations
                 |'''
    if len(p) == 5:
        p[0] = [p[1], p[3], p.lineno(1), p[4]]
    elif len(p) == 3:
        p[0] = [p[1], None, p.lineno(1), p[2]]


def p_struct(p):
    '''struct : seen_struct '{' field_seq '}' type_annotations'''
    cls, _, fields, _, annotations = p[1:6]
    val = _fill_in_struct(cls, fields)
    val.__thrift_annotations__ = _annotations_to_dict(annotations)
    _add_thrift_meta(p.parser.context.thrift_stack[-1], 'structs', val)


def p_seen_struct(p):
    '''seen_struct : STRUCT IDENTIFIER '''
    _, name = p[1:3]
    thrift = p.parser.context.thrift_stack[-1]
    val = _make_empty_struct(thrift, name, lineno=p.lineno(2))
    setattr(thrift, name, val)
    p[0] = val


def p_union(p):
    '''union : seen_union '{' field_seq '}' type_annotations'''
    cls, _, fields, _, annotations = p[1:6]
    val = _fill_in_struct(cls, fields)
    val.__thrift_annotations__ = _annotations_to_dict(annotations)
    _add_thrift_meta(p.parser.context.thrift_stack[-1], 'unions', val)


def p_seen_union(p):
    '''seen_union : UNION IDENTIFIER '''
    _, name = p[1:3]
    thrift = p.parser.context.thrift_stack[-1]
    val = _make_empty_struct(thrift, name, lineno=p.lineno(2))
    setattr(thrift, name, val)
    p[0] = val


def p_exception(p):
    '''exception : EXCEPTION IDENTIFIER '{' field_seq '}' type_annotations '''
    _, name, _, fields, _, annotations = p[1:7]
    thrift = p.parser.context.thrift_stack[-1]
    val = _make_struct(thrift, name, fields, base_cls=TException,
                       lineno=p.lineno(2))
    val.__thrift_annotations__ = _annotations_to_dict(annotations)
    setattr(thrift, name, val)
    _add_thrift_meta(thrift, 'exceptions', val)


def p_simple_service(p):
    '''simple_service : SERVICE IDENTIFIER '{' function_seq '}'
                | SERVICE IDENTIFIER EXTENDS IDENTIFIER '{' function_seq '}'
    '''
    thrift = p.parser.context.thrift_stack[-1]

    if len(p) == 8:
        extends = thrift
        for name in p[4].split('.'):
            extends = getattr(extends, name, None)
            if extends is None:
                raise ThriftParserError('Can\'t find service %r for '
                                        'service %r to extend' %
                                        (p[4], p[2]))

        if not hasattr(extends, 'thrift_services'):
            raise ThriftParserError('Can\'t extends %r, not a service'
                                    % p[4])

    else:
        extends = None

    p[0] = (p[2], p[len(p) - 2], extends, p.lineno(2))


def p_service(p):
    '''service : simple_service type_annotations'''
    service_info, annotations = p[1:3]
    name, funcs, extends, lineno = service_info
    thrift = p.parser.context.thrift_stack[-1]
    val = _make_service(thrift, name, funcs, extends, annotations,
                        lineno=lineno)
    setattr(thrift, name, val)
    _add_thrift_meta(thrift, 'services', val)


def p_simple_function(p):
    '''simple_function : ONEWAY function_type IDENTIFIER '(' field_seq ')'
    | ONEWAY function_type IDENTIFIER '(' field_seq ')' throws
    | function_type IDENTIFIER '(' field_seq ')' throws
    | function_type IDENTIFIER '(' field_seq ')' '''

    if p[1] == 'oneway':
        oneway = True
        base = 1
    else:
        oneway = False
        base = 0

    if p[len(p) - 1] == ')':
        throws = []
    else:
        throws = p[len(p) - 1]

    p[0] = [oneway, p[base + 1], p[base + 2], p[base + 4], throws,
            p.lineno(base + 2)]


def p_function(p):
    '''function : simple_function type_annotations'''
    p[0] = p[1] + [p[2]]


def p_function_seq(p):
    '''function_seq : function sep function_seq
                    | function function_seq
                    |'''
    _parse_seq(p)


def p_throws(p):
    '''throws : THROWS '(' field_seq ')' '''
    p[0] = p[3]


def p_function_type(p):
    '''function_type : field_type
                     | VOID'''
    if p[1] == 'void':
        p[0] = TType.VOID
    else:
        p[0] = p[1]


def p_field_seq(p):
    '''field_seq : field sep field_seq
                 | field field_seq
                 |'''
    p.parser.context.field_seq_implicit_id = \
        itertools.count(start=-1, step=-1)
    _parse_seq(p)


def p_simple_field(p):
    '''simple_field : field_id field_req field_type IDENTIFIER
             | field_id field_req field_type IDENTIFIER '=' const_value
             '''
    field_id, field_req, field_type, name = p[1:5]

    if len(p) == 7:
        try:
            default_val = _cast(field_type)(p[6])
        except AssertionError:
            raise ThriftParserError(
                'Type error for field %s '
                'at line %d' % (name, p.lineno(4)))
    else:
        default_val = None

    p[0] = [field_id, field_req, field_type, name, default_val,
            p.lineno(4)]


def p_field(p):
    '''field : simple_field type_annotations'''
    p[0] = p[1] + [p[2]]


def p_field_id(p):
    '''field_id : INTCONSTANT ':'
                |'''
    if len(p) == 1:
        p[0] = next(p.parser.context.field_seq_implicit_id)
    else:
        p[0] = p[1]


def p_field_req(p):
    '''field_req : REQUIRED
                 | OPTIONAL
                 |'''
    if len(p) == 2:
        p[0] = p[1] == 'required'
    elif len(p) == 1:
        p[0] = False  # default: required=False


def p_field_type(p):
    '''field_type : ref_type
                  | definition_type'''
    p[0] = p[1]


class CurrentIncompleteType(dict):
    index = -1

    def set_info(self, info):
        self[self.index] = info
        self.index -= 1
        return self.index + 1


# Memoization of parsed modules, keyed by module name / normalized path. It
# persists across `parse`/`load` calls so repeated loads of the same file
# return the same module object (and therefore the same generated classes,
# keeping ``isinstance`` checks working). Sharing it process-wide is safe
# because every access happens under `_parse_lock`.
_thrift_cache = {}

# Serializes parsing across threads. PLY's `lex.lex()` / `yacc.yacc()` and
# `parser.parse()` mutate module-global state and are not concurrency-safe, and
# the cache lookup/build/write must be atomic so two threads can't each miss
# the cache and build divergent modules for the same key. A re-entrant lock is
# required because `include` handling re-enters `parse` on the same thread.
_parse_lock = threading.RLock()


class ParseContext(object):
    """Per parse-tree state, shared across recursive `include` parsing.

    Grammar rule callbacks reach the current context through ``p.parser.context``
    instead of relying on module-level or thread-local ambient state. Each
    top-level parse gets its own context, so no state leaks between parse
    invocations (including across threads and asyncio coroutines). Note the
    parsing itself is still serialized by ``_parse_lock`` because PLY is not
    concurrency-safe.
    """

    def __init__(self):
        self.thrift_stack = []
        self.include_dirs = ['.']
        self.incomplete_type = CurrentIncompleteType()
        self.field_seq_implicit_id = itertools.count(start=-1, step=-1)


def p_ref_type(p):
    '''ref_type : IDENTIFIER'''
    ref_type = p.parser.context.thrift_stack[-1]

    for attr in dir(ref_type):
        if attr in {'__doc__', '__loader__', '__name__', '__package__',
                    '__spec__', '__thrift_file__', '__thrift_meta__'}:
            continue
        if p[1].startswith(attr + '.'):
            name = p[1][len(attr) + 1:]
            included_ref_type = getattr(ref_type, attr)
            resolved_ref_type = getattr(included_ref_type, name, None)
            if resolved_ref_type is not None:
                ref_type = resolved_ref_type
                break
    else:
        for index, name in enumerate(p[1].split('.')):
            ref_type = getattr(ref_type, name, None)
            if ref_type is None:
                if index != len(p[1].split('.')) - 1:
                    raise ThriftParserError('No type found: %r, at line %d' %
                                            (p[1], p.lineno(1)))
                p[0] = p.parser.context.incomplete_type.set_info(
                    (p[1], p.lineno(1)))
                return

    if hasattr(ref_type, '_ttype'):
        p[0] = getattr(ref_type, '_ttype'), ref_type
    else:
        p[0] = ref_type


def p_simple_base_type(p):  # noqa
    '''simple_base_type : BOOL
                        | BYTE
                        | I8
                        | I16
                        | I32
                        | I64
                        | DOUBLE
                        | STRING
                        | BINARY'''
    if p[1] == 'bool':
        p[0] = TType.BOOL
    if p[1] == 'byte' or p[1] == 'i8':
        p[0] = TType.BYTE
    if p[1] == 'i16':
        p[0] = TType.I16
    if p[1] == 'i32':
        p[0] = TType.I32
    if p[1] == 'i64':
        p[0] = TType.I64
    if p[1] == 'double':
        p[0] = TType.DOUBLE
    if p[1] == 'string':
        p[0] = TType.STRING
    if p[1] == 'binary':
        p[0] = TType.BINARY


def p_base_type(p):
    '''base_type : simple_base_type type_annotations'''
    p[0] = p[1]


def p_simple_container_type(p):
    '''simple_container_type : map_type
                             | list_type
                             | set_type'''
    p[0] = p[1]


def p_container_type(p):
    '''container_type : simple_container_type type_annotations'''
    p[0] = p[1]


def p_map_type(p):
    '''map_type : MAP '<' field_type ',' field_type '>' '''
    p[0] = TType.MAP, (p[3], p[5])


def p_list_type(p):
    '''list_type : LIST '<' field_type '>' '''
    p[0] = TType.LIST, p[3]


def p_set_type(p):
    '''set_type : SET '<' field_type '>' '''
    p[0] = TType.SET, p[3]


def p_definition_type(p):
    '''definition_type : base_type
                       | container_type'''
    p[0] = p[1]


def p_type_annotations(p):
    '''type_annotations : '(' type_annotation_seq ')'
                        |'''
    if len(p) == 4:
        p[0] = p[2]
    else:
        p[0] = None


def p_type_annotation_seq(p):
    '''type_annotation_seq : type_annotation sep type_annotation_seq
                           | type_annotation type_annotation_seq
                           |'''
    _parse_seq(p)


def p_type_annotation(p):
    '''type_annotation : IDENTIFIER '=' LITERAL
                       | IDENTIFIER '''
    if len(p) == 4:
        p[0] = p[1], p[3]
    else:
        p[0] = p[1], None  # Without Value


def parse(path, module_name=None, include_dirs=None, include_dir=None,
          lexer=None, parser=None, enable_cache=True, encoding='utf-8',
          _context=None):
    """Parse a single thrift file to module object, e.g.::

        >>> from thriftpy2.parser.parser import parse
        >>> note_thrift = parse("path/to/note.thrift")
        <module 'note_thrift' (built-in)>

    :param path: file path to parse, should be a string ending with '.thrift'.
    :param module_name: the name for parsed module, the default is the basename
                        without extension of `path`.
    :param include_dirs: directories to find thrift files while processing
                         the `include` directive, by default: ['.'].
    :param include_dir: directory to find child thrift files. Note this keyword
                        parameter will be deprecated in the future, it exists
                        for compatible reason. If it's provided (not `None`),
                        it will be appended to `include_dirs`.
    :param lexer: ply lexer to use, if not provided, `parse` will new one.
    :param parser: ply parser to use, if not provided, `parse` will new one.
    :param enable_cache: if this is set to be `True`, parsed module will be
                         cached, this is enabled by default. If `module_name`
                         is provided, use it as cache key, else use the `path`.
    """
    # `_context` is shared across recursive `include` parsing; a top-level
    # call creates a fresh one so no state leaks between parse invocations.
    context = _context if _context is not None else ParseContext()

    # dead include checking on current stack
    for thrift in context.thrift_stack:
        if thrift.__thrift_file__ is not None and \
                os.path.samefile(path, thrift.__thrift_file__):
            raise ThriftParserError('Dead including on %s' % path)

    cache_key = module_name or os.path.normpath(path)

    with _parse_lock:
        if enable_cache and cache_key in _thrift_cache:
            return _thrift_cache[cache_key]

        if include_dirs is not None:
            context.include_dirs = include_dirs
        if include_dir is not None:
            context.include_dirs.append(include_dir)

        if not path.endswith('.thrift'):
            raise ThriftParserError('Path should end with .thrift')

        url_scheme = urlparse(path).scheme
        if url_scheme == 'file':
            with open(urlparse(path).netloc + urlparse(path).path) as fh:
                data = fh.read()
        elif len(url_scheme) <= 1:
            with open(path, encoding=encoding) as fh:
                data = fh.read()
        elif url_scheme in ('http', 'https'):
            data = urlopen(path).read()
        else:
            raise ThriftParserError('thriftpy2 does not support generating '
                                    'module with path in protocol \'{}\''
                                    .format(url_scheme))

        if isinstance(data, bytes):
            data = data.decode(encoding)

        if module_name is not None and not module_name.endswith('_thrift'):
            raise ThriftParserError('thriftpy2 can only generate module with '
                                    '\'_thrift\' suffix')

        if module_name is None:
            basename = os.path.basename(path)
            module_name = os.path.splitext(basename)[0]

        thrift = types.ModuleType(module_name)
        setattr(thrift, '__thrift_file__', path)
        _parse_data(data, thrift, context, lexer, parser,
                    is_root=_context is None)

        if enable_cache:
            _thrift_cache[cache_key] = thrift
        return thrift


def parse_fp(source, module_name, lexer=None, parser=None, enable_cache=True,
             _context=None):
    """Parse a file-like object to thrift module object, e.g.::

        >>> from thriftpy2.parser.parser import parse_fp
        >>> with open("path/to/note.thrift") as fp:
                parse_fp(fp, "note_thrift")
        <module 'note_thrift' (built-in)>

    :param source: file-like object, expected to have a method named `read`.
    :param module_name: the name for parsed module, should be endswith
                        '_thrift'.
    :param lexer: ply lexer to use, if not provided, `parse` will new one.
    :param parser: ply parser to use, if not provided, `parse` will new one.
    :param enable_cache: if this is set to be `True`, parsed module will be
                         cached by `module_name`, this is enabled by default.
    """
    context = _context if _context is not None else ParseContext()

    if not module_name.endswith('_thrift'):
        raise ThriftParserError('thriftpy2 can only generate module with '
                                '\'_thrift\' suffix')

    if not hasattr(source, 'read'):
        raise ThriftParserError('Expected `source` to be a file-like object '
                                'with a method named \'read\'')

    with _parse_lock:
        if enable_cache and module_name in _thrift_cache:
            return _thrift_cache[module_name]

        data = source.read()

        # When `source` is a real file object its `name` gives us the path the
        # thrift text came from, so `include` statements can be resolved
        # relative to it just like in `parse`.
        source_path = getattr(source, 'name', None)
        if not isinstance(source_path, str) or not os.path.isfile(source_path):
            source_path = None

        thrift = types.ModuleType(module_name)
        setattr(thrift, '__thrift_file__', source_path)
        _parse_data(data, thrift, context, lexer, parser,
                    is_root=_context is None)

        if enable_cache:
            _thrift_cache[module_name] = thrift
        return thrift


def _parse_data(data, thrift, context, lexer, parser, is_root):
    """Run the PLY parser over ``data``, populating the ``thrift`` module.

    Shared tail of `parse`/`parse_fp`; the caller must hold ``_parse_lock``.
    At the root of the parse tree (the call that created the context), forward
    references are resolved right away -- while still holding the lock and
    before the module is published to the cache -- so the cache never exposes
    a module that still contains negative placeholder ttypes.
    """
    if lexer is None:
        lexer = lex.lex()
    if parser is None:
        parser = yacc.yacc(debug=False, write_tables=False)

    context.thrift_stack.append(thrift)
    parser.context = context
    lexer.lineno = 1
    try:
        parser.parse(data)
    except _GrammarError as e:
        if e.value is None:
            raise ThriftGrammarError(
                "Grammar error at EOF of the file '%s'"
                % thrift.__thrift_file__) from None
        raise ThriftGrammarError(
            "Grammar error %r at line %d of the file '%s'"
            % (e.value, e.lineno, thrift.__thrift_file__)) from None
    context.thrift_stack.pop()

    if is_root and context.incomplete_type:
        _fill_incomplete_ttype(thrift, thrift, context.incomplete_type)


def _fill_incomplete_ttype(tmodule, definition, incomplete_type):
    """Second pass of parser to handle out-of-order definitions.

    ``incomplete_type`` is the placeholder map collected during parsing
    (``ParseContext.incomplete_type``); it is threaded through explicitly so
    the second pass never relies on ambient state. Run at the root of the parse
    tree before the module is published to the cache.
    """
    # construct incomplete types' thrift_spec
    if isinstance(definition, tuple):
        # construct const value
        if definition[0] == 'UNKNOWN_CONST':
            ttype = _get_definition(
                tmodule, incomplete_type[definition[1]][0], definition[3],
                incomplete_type)
            return _cast(ttype)(definition[2])
        # construct incomplete alias type
        elif definition[1] in incomplete_type:
            return (
                definition[0],
                _get_definition(tmodule, *incomplete_type[definition[1]],
                                incomplete_type=incomplete_type)
            )
        # construct incomplete type which is contained in service method's args
        elif definition[0] in incomplete_type:
            real_type = _get_definition(
                tmodule, *incomplete_type[definition[0]],
                incomplete_type=incomplete_type
            )
            assert isinstance(real_type, tuple)
            return (real_type[0], definition[1], real_type[1], definition[2])
        # construct incomplete compound type
        elif isinstance(definition[1], tuple):
            return (
                definition[0],
                _fill_incomplete_ttype(tmodule, definition[1], incomplete_type)
            )
    # if type is a thrift module, search it if there are incomplete types
    elif isinstance(definition, types.ModuleType):
        for name, attr in definition.__dict__.items():
            if name.startswith('__'):  # skip inner attribute
                continue
            setattr(definition, name,
                    _fill_incomplete_ttype(definition, attr, incomplete_type))
    # if type is a struct, search it if there are incomplete types
    elif isinstance(definition, TPayloadMeta):
        for index, value in definition.thrift_spec.items():
            # if the ttype of the field is a single type and it is incompleted
            if value[0] in incomplete_type:
                real_type = _fill_incomplete_ttype(
                    tmodule, _get_definition(
                        tmodule, *incomplete_type[value[0]],
                        incomplete_type=incomplete_type
                    ), incomplete_type
                )
                # if the incomplete ttype is a compound type
                if isinstance(real_type, tuple):
                    definition.thrift_spec[index] = (
                        real_type[0],
                        value[1],
                        real_type[1],
                        value[2]
                    )
                # if the incomplete ttype is a built-in ttype
                else:
                    definition.thrift_spec[index] = (
                        _fill_incomplete_ttype(
                            tmodule, _get_definition(
                                tmodule, *incomplete_type[value[0]],
                                incomplete_type=incomplete_type
                            ), incomplete_type
                        ),
                    ) + tuple(value[1:])
            # if the field's ttype is a compound type
            # and it contains incomplete types
            elif value[2] in incomplete_type:
                definition.thrift_spec[index] = (
                    value[0],
                    value[1],
                    _fill_incomplete_ttype(
                        tmodule, _get_definition(
                            tmodule, *incomplete_type[value[2]],
                            incomplete_type=incomplete_type
                        ), incomplete_type
                    ),
                    value[3])
            # if the field's ttype is a nest compound type
            # and it contains incomplete type
            elif isinstance(value[2], tuple):
                def walk(part):
                    if isinstance(part, tuple):
                        return tuple(walk(x) for x in part)
                    if part in incomplete_type:
                        return _get_definition(
                            tmodule, *incomplete_type[part],
                            incomplete_type=incomplete_type)
                    return part
                definition.thrift_spec[index] = (
                    value[0],
                    value[1],
                    walk(value[2]),
                    value[3])
    # if it is a service method definition
    elif hasattr(definition, "thrift_services"):
        for name, attr in definition.__dict__.items():
            if not hasattr(attr, "thrift_spec"):
                continue
            for index, value in attr.thrift_spec.items():
                attr.thrift_spec[index] = _fill_incomplete_ttype(
                    tmodule, value, incomplete_type)
    return definition


def _get_definition(thrift, name, lineno, incomplete_type):
    """Get definition from thrift module and incomplete type map.
    """
    ref_type = thrift
    for n in name.split('.'):
        ref_type = getattr(thrift, n, None)
        if ref_type is None:
            raise ThriftParserError('No type found: %r, at line %d' %
                                    (name, lineno))
        if isinstance(ref_type, int) and ref_type < 0:
            raise ThriftParserError('No type found: %r, at line %d' %
                                    incomplete_type[ref_type])
        if hasattr(ref_type, '_ttype'):
            return (getattr(ref_type, '_ttype'), ref_type)
        else:
            return ref_type


def _add_thrift_meta(thrift, key, val):
    if not hasattr(thrift, '__thrift_meta__'):
        meta = collections.defaultdict(list)
        setattr(thrift, '__thrift_meta__', meta)
    else:
        meta = getattr(thrift, '__thrift_meta__')

    if key != 'consts' and val.__name__ in [x.__name__ for x in meta[key]]:
        raise ThriftGrammarError(('\'%s\' type is already defined in '
                                  '\'%s\'') % (val.__name__, key))

    meta[key].append(val)


def _parse_seq(p):
    if len(p) == 4:
        p[0] = [p[1]] + p[3]
    elif len(p) == 3:
        p[0] = [p[1]] + p[2]
    elif len(p) == 1:
        p[0] = []


def _cast(t: Any, linno: int = 0) -> Any:  # noqa
    if isinstance(t, int) and t < 0:
        return _lazy_cast_const(t, linno)
    if t == TType.BOOL:
        return _cast_bool
    if t == TType.BYTE:
        return _cast_byte
    if t == TType.I16:
        return _cast_i16
    if t == TType.I32:
        return _cast_i32
    if t == TType.I64:
        return _cast_i64
    if t == TType.DOUBLE:
        return _cast_double
    if t == TType.STRING:
        return _cast_string
    if t == TType.BINARY:
        return _cast_binary
    if t[0] == TType.LIST:
        return _cast_list(t)
    if t[0] == TType.SET:
        return _cast_set(t)
    if t[0] == TType.MAP:
        return _cast_map(t)
    if t[0] == TType.I32:
        return _cast_enum(t)
    if t[0] == TType.STRUCT:
        return _cast_struct(t)


def _lazy_cast_const(t, linno):
    def _inner_cast(v):
        return ('UNKNOWN_CONST', t, v, linno)
    return _inner_cast


def _cast_bool(v):
    assert isinstance(v, (bool, int))
    return bool(v)


def _cast_byte(v):
    assert isinstance(v, int)
    return v


def _cast_i16(v):
    assert isinstance(v, int)
    return v


def _cast_i32(v):
    assert isinstance(v, int)
    return v


def _cast_i64(v):
    assert isinstance(v, int)
    return v


def _cast_double(v):
    assert isinstance(v, (float, int))
    return float(v)


def _cast_string(v):
    assert isinstance(v, str)
    return v


def _cast_binary(v):
    assert isinstance(v, str)
    return v


def _cast_list(t):
    assert t[0] == TType.LIST

    def __cast_list(v):
        assert isinstance(v, list)
        map(_cast(t[1]), v)
        return v
    return __cast_list


def _cast_set(t):
    assert t[0] == TType.SET

    def __cast_set(v):
        if len(v) == 0 and isinstance(v, dict):
            v = set()
        assert isinstance(v, (list, set))
        map(_cast(t[1]), v)
        if not isinstance(v, set):
            return set(v)
        return v
    return __cast_set


def _cast_map(t):
    assert t[0] == TType.MAP

    def __cast_map(v):
        assert isinstance(v, dict)
        for key in v:
            v[_cast(t[1][0])(key)] = \
                _cast(t[1][1])(v[key])
        return v
    return __cast_map


def _cast_enum(t):
    assert t[0] == TType.I32

    def __cast_enum(v):
        assert isinstance(v, int)
        if v in t[1]._VALUES_TO_NAMES:
            return v
        raise ThriftParserError('Couldn\'t find a named value in enum '
                                '%s for value %d' % (t[1].__name__, v))
    return __cast_enum


def _cast_struct(t):   # struct/exception/union
    assert t[0] == TType.STRUCT

    def __cast_struct(v):
        if isinstance(v, t[1]):
            return v  # already cast

        assert isinstance(v, dict)
        tspec = getattr(t[1], '_tspec')

        for key in tspec:  # requirement check
            if tspec[key][0] and key not in v:
                raise ThriftParserError('Field %r was required to create '
                                        'constant for type %r' %
                                        (key, t[1].__name__))

        for key in v:  # cast values
            if key not in tspec:
                raise ThriftParserError('No field named %r was '
                                        'found in struct of type %r' %
                                        (key, t[1].__name__))
            v[key] = _cast(tspec[key][1])(v[key])
        return t[1](**v)
    return __cast_struct


def _make_enum(thrift, name, kvs, annotations=None, lineno=None):
    attrs = {
        '__module__': thrift.__name__,
        '_ttype': TType.I32,
        '__thrift_lineno__': lineno,
        '__thrift_file__': getattr(thrift, '__thrift_file__', None)
    }
    cls = type(name, (object, ), attrs)

    _values_to_names = {}
    _names_to_values = {}
    item_linenos = {}
    item_annotations = {}

    if kvs:
        val = kvs[0][1]
        if val is None:
            val = -1
        for item in kvs:
            if item[1] is None:
                item[1] = val + 1
            val = item[1]
        for key, val, item_lineno, annotation in kvs:
            setattr(cls, key, val)
            _values_to_names[val] = key
            _names_to_values[key] = val
            item_linenos[key] = item_lineno
            if annotation:
                item_annotations[key] = _annotations_to_dict(annotation)
    setattr(cls, '_VALUES_TO_NAMES', _values_to_names)
    setattr(cls, '_NAMES_TO_VALUES', _names_to_values)
    setattr(cls, '__thrift_item_linenos__', item_linenos)
    setattr(cls, '__thrift_annotations__', _annotations_to_dict(annotations))
    setattr(cls, '__thrift_item_annotations__', item_annotations)
    return cls


def _make_empty_struct(thrift, name, ttype=TType.STRUCT, base_cls=TPayload,
                       lineno=None):
    attrs = {
        '__module__': thrift.__name__,
        '_ttype': ttype,
        '__thrift_lineno__': lineno,
        '__thrift_file__': getattr(thrift, '__thrift_file__', None)
    }
    return type(name, (base_cls, ), attrs)


def _fill_in_struct(cls, fields, _gen_init=True):
    thrift_spec = {}
    default_spec = []
    _tspec = {}
    field_linenos = {}
    field_annotations = {}

    for field in fields:
        if field[0] in thrift_spec or field[3] in _tspec:
            raise ThriftGrammarError(('\'%d:%s\' field identifier/name has '
                                      'already been used') % (field[0],
                                                              field[3]))
        ttype = field[2]
        thrift_spec[field[0]] = _ttype_spec(ttype, field[3], field[1])
        default_spec.append((field[3], field[4]))
        _tspec[field[3]] = field[1], ttype
        field_linenos[field[3]] = field[5]
        if len(field) > 6 and field[6]:
            field_annotations[field[3]] = _annotations_to_dict(field[6])
    setattr(cls, 'thrift_spec', thrift_spec)
    setattr(cls, 'default_spec', default_spec)
    setattr(cls, '_tspec', _tspec)
    setattr(cls, '__thrift_field_linenos__', field_linenos)
    setattr(cls, '__thrift_field_annotations__', field_annotations)
    if _gen_init:
        gen_init(cls, thrift_spec, default_spec)
    return cls


def _make_struct(thrift, name, fields, ttype=TType.STRUCT, base_cls=TPayload,
                 _gen_init=True, lineno=None):
    cls = _make_empty_struct(thrift, name, ttype=ttype, base_cls=base_cls,
                             lineno=lineno)
    return _fill_in_struct(cls, fields, _gen_init=_gen_init)


def _make_service(thrift, name, funcs, extends, annotations=None, lineno=None):
    if extends is None:
        extends = object

    attrs = {
        '__module__': thrift.__name__,
        '__thrift_lineno__': lineno,
        '__thrift_file__': getattr(thrift, '__thrift_file__', None)
    }
    cls = type(name, (extends, ), attrs)
    thrift_services = []
    # inherited functions keep the lineno of the service that defined
    # them, relative to that service's __thrift_file__
    function_linenos = dict(getattr(extends, '__thrift_function_linenos__',
                                    {}))
    function_annotations = {}

    for func in funcs:
        func_name = func[2]
        if func_name in thrift_services:
            raise ThriftGrammarError(('\'%s\' function is already defined in '
                                      'service \'%s\'') % (func_name,
                                                           name))
        # args payload cls
        args_name = '%s_args' % func_name
        args_fields = func[3]
        args_cls = _make_struct(thrift, args_name, args_fields)
        setattr(cls, args_name, args_cls)
        # result payload cls
        result_name = '%s_result' % func_name
        result_type = func[1]
        result_throws = func[4]
        result_oneway = func[0]
        result_cls = _make_struct(thrift, result_name, result_throws,
                                  _gen_init=False)
        setattr(result_cls, 'oneway', result_oneway)
        if result_type != TType.VOID:
            result_cls.thrift_spec[0] = _ttype_spec(result_type, 'success')
            result_cls.default_spec.insert(0, ('success', None))
        gen_init(result_cls, result_cls.thrift_spec, result_cls.default_spec)
        setattr(cls, result_name, result_cls)
        thrift_services.append(func_name)
        function_linenos[func_name] = func[5]
        if len(func) > 6 and func[6]:
            function_annotations[func_name] = _annotations_to_dict(func[6])
    if extends is not None and hasattr(extends, 'thrift_services'):
        thrift_services.extend(getattr(extends, 'thrift_services'))
    setattr(cls, 'thrift_services', thrift_services)
    setattr(cls, '__thrift_function_linenos__', function_linenos)
    setattr(cls, '__thrift_annotations__', _annotations_to_dict(annotations))
    setattr(cls, '__thrift_function_annotations__', function_annotations)
    return cls


def _ttype_spec(ttype, name, required=False):
    if isinstance(ttype, int):
        return ttype, name, required
    else:
        return ttype[0], name, ttype[1], required


def _get_ttype(inst, default_ttype=None):
    if hasattr(inst, '__dict__') and '_ttype' in inst.__dict__:
        return inst.__dict__['_ttype']
    return default_ttype
