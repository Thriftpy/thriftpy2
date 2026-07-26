namespace * default_ns
namespace py foo.bar
namespace py.twisted foo.bar.twisted
namespace java com.example.foo

// duplicated scope, the last declaration wins
namespace py foo.baz

struct Foo {
    1: required i32 a,
}
