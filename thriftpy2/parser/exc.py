from warnings import warn


class ThriftParserError(Exception):
    pass


class ThriftModuleNameConflict(ThriftParserError):
    pass


class ThriftLexerError(ThriftParserError):
    pass


class ThriftGrammarError(ThriftParserError):
    pass


def __getattr__(name: str) -> type[ThriftGrammarError]:
    if name == "ThriftGrammerError":
        warn("'ThriftGrammerError' is a typo of 'ThriftGrammarError'", DeprecationWarning)
        return ThriftGrammarError

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
