// Test case for when a local struct has the same name as an imported module
include "name_collision_imported.thrift"

// Local struct with the same name as the imported module
struct name_collision_imported {
    1: required string local_field1
    2: optional i32 local_field2
}

struct TestStruct {
    // Should resolve to local struct 'name_collision_imported'
    1: required name_collision_imported localStruct

    // Should resolve to UserProfile from the imported module
    2: required name_collision_imported.UserProfile importedUserProfile
}