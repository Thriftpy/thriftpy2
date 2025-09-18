#!/usr/bin/env python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import thriftpy2

def test_naming_collision():
    """Test that qualified references work correctly when local struct has same name as imported module."""

    # Load the main thrift file
    main_thrift = thriftpy2.load("main.thrift", module_name="main_thrift",
                                  include_dirs=[os.path.dirname(__file__)])

    print("Testing name resolution bug...")
    print("-" * 50)

    # Check what's in the module
    print(f"Attributes in main_thrift: {[attr for attr in dir(main_thrift) if not attr.startswith('_')]}")
    print()

    # Check the local struct
    print(f"Local struct 'user_types': {main_thrift.user_types}")
    print(f"Local struct fields: {main_thrift.user_types.thrift_spec}")
    print()

    # Check the imported module
    print(f"Imported module 'user_types': {getattr(main_thrift, 'user_types', 'NOT FOUND')}")

    # Try to access UserProfile from imported module
    if hasattr(main_thrift.user_types, 'UserProfile'):
        print(f"user_types.UserProfile found: {main_thrift.user_types.UserProfile}")
        print(f"UserProfile fields: {main_thrift.user_types.UserProfile.thrift_spec}")
    else:
        print("ERROR: Cannot access UserProfile from user_types module!")
    print()

    # Check ApplicationData structure
    print(f"ApplicationData: {main_thrift.ApplicationData}")
    print(f"ApplicationData fields: {main_thrift.ApplicationData.thrift_spec}")
    print()

    # Analyze the field types
    for field_id, field_spec in main_thrift.ApplicationData.thrift_spec.items():
        field_name = field_spec[1]
        field_type = field_spec[2] if len(field_spec) > 2 else field_spec[0]
        print(f"Field {field_id} ({field_name}): type = {field_type}")

        # Check if both fields incorrectly point to the same type
        if field_id == 1:
            local_type = field_type
        elif field_id == 2:
            imported_type = field_type
            if local_type == imported_type:
                print("ERROR: Both fields resolve to the same type (local struct)!")
                print("       Field 2 should resolve to UserProfile from imported module!")
                return False

    print("\nTest PASSED: Name resolution works correctly!")
    return True

if __name__ == "__main__":
    try:
        success = test_naming_collision()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)