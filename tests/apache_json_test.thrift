exception TestException {
    1: string message
}
struct Foo {
    1: string bar
}
struct Test {
    1: bool tbool,
    2: i8 tbyte,
    3: i16 tshort,
    4: i32 tint,
    5: i64 tlong,
    6: double tdouble,
    7: string tstr,
    8: list<string> tlist_of_strings,
    9: map<i32, string> tmap_of_int2str,
    10: set<i32> tsetofints,
    11: map<string, Foo> tmap_of_str2foo,
    12: map<string, list<string>> tmap_of_str2stringlist,
    13: map<string, map<string, Foo>> tmap_of_str2mapofstring2foo,
    14: list<Foo> tlist_of_foo,
    15: Foo tfoo,
    16: list<map<string, i32>> tlist_of_maps2int,
    17: map<string, list<Foo>> tmap_of_str2foolist,
    18: map<i32, Foo> tmap_of_int2foo,
    19: binary tbinary,
    20: optional map<bool, string> tmap_of_bool2str
    21: optional map<bool, i16> tmap_of_bool2int,
    22: list<binary> tlist_of_binary,
    23: set<binary> tset_of_binary,
    24: map<binary,binary> tbin2bin,
}

service TestService {
    // Testing Service that just returns what you give it
    Test test(1: Test test);
    void do_error(1: string arg) throws (
        1: TestException e
    )
}
