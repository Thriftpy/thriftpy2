import io
from pathlib import Path

from thriftpy2 import load, load_fp


TEST_DIR = Path(__file__).parent


def test_struct_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.Person.__thrift_lineno__ == 1
    assert thrift.Person.__thrift_file__.endswith('lineno.thrift')
    assert thrift.Person.__thrift_field_linenos__ == {'name': 2, 'address': 3}


def test_enum_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.Color.__thrift_lineno__ == 6
    assert thrift.Color.__thrift_file__.endswith('lineno.thrift')
    assert thrift.Color.__thrift_item_linenos__ == {'RED': 7, 'GREEN': 8, 'BLUE': 9}


def test_union_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.Value.__thrift_lineno__ == 12
    assert thrift.Value.__thrift_field_linenos__ == {'sval': 13, 'ival': 14}


def test_exception_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.NetworkError.__thrift_lineno__ == 17
    assert thrift.NetworkError.__thrift_field_linenos__ == {
        'error_code': 18, 'message': 19}


def test_service_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.BaseService.__thrift_lineno__ == 22
    assert thrift.BaseService.__thrift_file__.endswith('lineno.thrift')
    assert thrift.BaseService.__thrift_function_linenos__ == {'ping': 23}


def test_extended_service_linenos():
    thrift = load(TEST_DIR / 'parser-cases/lineno.thrift')

    assert thrift.ChildService.__thrift_lineno__ == 26
    # inherited functions keep the lineno where the parent defined them
    assert thrift.ChildService.__thrift_function_linenos__ == {
        'ping': 23, 'notify': 27, 'hello': 28}
    for name in thrift.ChildService.thrift_services:
        assert name in thrift.ChildService.__thrift_function_linenos__


def test_load_fp_linenos():
    content = ('struct Foo {\n'
               '    1: string bar,\n'
               '}\n')
    thrift = load_fp(io.StringIO(content), 'foo_thrift')

    assert thrift.Foo.__thrift_lineno__ == 1
    assert thrift.Foo.__thrift_file__ is None
    assert thrift.Foo.__thrift_field_linenos__ == {'bar': 2}


def test_include_file_path():
    thrift = load(TEST_DIR / 'parser-cases/include.thrift', include_dirs=[
        TEST_DIR / 'parser-cases'], module_name='include_thrift')

    assert thrift.__thrift_file__.endswith('include.thrift')
    assert thrift.included.__thrift_file__.endswith('included.thrift')
