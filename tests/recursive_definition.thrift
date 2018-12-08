service PingPong {
    Foo echo(1:Foo param)
}

struct Foo {
    1: optional Bar test,
    2: optional Some some,
}

struct Bar {
    1: optional Foo test,
}

typedef i32 Some
