include "user_types.thrift"

struct user_types {
    1: required string local_field1
    2: optional i32 local_field2
}

struct ApplicationData {
    // Case 1a: Reference to local struct that has same name as imported module
    1: required user_types localUserTypes

    // Case 1b: SHOULD reference user_types.UserProfile from imported module
    // BUT will incorrectly resolve to local user_types struct
    2: required user_types.UserProfile importedUserProfile
}