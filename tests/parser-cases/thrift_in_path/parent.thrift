include "main/thrift/sub/child.thrift"

struct ParentStruct {
    1: required child.ChildStruct child
}
