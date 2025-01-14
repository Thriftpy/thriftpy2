# -*- coding: utf-8 -*-

from __future__ import absolute_import

import sys
from warnings import warn


class ThriftParserError(Exception):
    pass


class ThriftModuleNameConflict(ThriftParserError):
    pass


class ThriftLexerError(ThriftParserError):
    pass


class ThriftGrammarError(ThriftParserError):
    pass


if sys.version_info >= (3, 7):
    def __getattr__(name):
        if name == "ThriftGrammerError":
            warn("'ThriftGrammerError' is a typo of 'ThriftGrammarError'", DeprecationWarning)
            return ThriftGrammarError

        raise AttributeError("module %r has no attribute %r" % (__name__, name))
else:
    ThriftGrammerError = ThriftGrammarError
