include "issue_177_include.thrift"

struct Issue177 {
    1: issue_177_include.Status status
    2: issue_177_include.invalidType type
}
