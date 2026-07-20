struct Person {
    1: string name,
    2: string address,
}

enum Color {
    RED = 1,
    GREEN,
    BLUE = 10,
}

union Value {
    1: string sval,
    2: i32 ival,
}

exception NetworkError {
    1: i32 error_code,
    2: string message,
}

service BaseService {
    void ping(),
}

service ChildService extends BaseService {
    oneway void notify(1: string message),
    string hello(1: string name) throws (1: NetworkError err),
}
