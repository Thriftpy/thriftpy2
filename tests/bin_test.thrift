struct BinTest {
    1: binary tbinary,
    2: map<string, binary> str2bin,
    3: map<binary, binary> bin2bin,
    4: map<binary, string> bin2str,
    5: list<binary> binlist,
    6: set<binary> binset,
    7: map<string, list<binary>> map_of_str2binlist,
    8: map<binary, map<binary, binary>> map_of_bin2bin,
    9: optional list<map<binary, string>> list_of_bin2str
}
service BinService {
    // Testing Service that just returns what you give it
    BinTest test(1: BinTest test);
}
