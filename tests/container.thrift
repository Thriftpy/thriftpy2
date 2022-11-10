struct ListStruct {
    1: optional list<ListItem> list_items,
}

struct ListItem {
    1: optional list<string> list_string,
    2: optional list<list<string>> list_list_string,
}

struct MapItem {
    1: optional map<string, string> map_string,
    2: optional map<string, map<string, string>> map_map_string,
}

struct MixItem {
    1: optional list<map<string, string>> list_map,
    2: optional map<string, list<string>> map_list,
}

struct BinListStruct {
    1: optional list<ListItem> list_items,
}

struct BinListItem {
    1: optional list<binary> list_binary,
    2: optional list<list<binary>> list_list_binary,
}

struct BinMapItem {
    1: optional map<binary, binary> map_binary,
    2: optional map<binary, map<binary, binary>> map_map_binary,
}

struct BinMixItem {
    1: optional list<map<binary, binary>> list_map,
    2: optional map<binary, list<binary>> map_list,
}
