struct Person {
    1: string name,
    2: string address
}

struct MetaData {
    1: set<string> tags = {}
}

struct Email {
    1: string subject = 'Subject',
    2: string content,
    3: Person sender,
    4: required Person recver,
    5: MetaData metadata
}

struct Dog {
    string name;
    1: i32 age;
    string nickname;
}

struct Cat {
    string name;
}


const Email email = {'subject': 'Hello', 'content': 'Long time no see',
    'sender': {'name': 'jack', 'address': 'jack@gmail.com'},
    'recver': {'name': 'chao', 'address': 'chao@gmail.com'},
    'metadata': {},
}
