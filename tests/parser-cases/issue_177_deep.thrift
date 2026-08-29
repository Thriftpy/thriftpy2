include "issue_177_deep_include.thrift"

struct Issue177Deep {
    1: issue_177_deep_include.NEG.Foo foo
}
