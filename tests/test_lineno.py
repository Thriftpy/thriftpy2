import pytest

from thriftpy2.parser import load


def test_struct_field_linenos():
    """Test that struct fields have correct lineno information."""
    thrift = load('parser-cases/structs.thrift')

    assert hasattr(thrift.Person, '_field_linenos')
    assert thrift.Person._field_linenos['name'] == 2
    assert thrift.Person._field_linenos['address'] == 3

    assert hasattr(thrift.Email, '_field_linenos')
    assert thrift.Email._field_linenos['subject'] == 11
    assert thrift.Email._field_linenos['content'] == 12
    assert thrift.Email._field_linenos['sender'] == 13
    assert thrift.Email._field_linenos['recver'] == 14
    assert thrift.Email._field_linenos['metadata'] == 15

    assert hasattr(thrift.Dog, '_field_linenos')
    assert thrift.Dog._field_linenos['name'] == 19
    assert thrift.Dog._field_linenos['age'] == 20
    assert thrift.Dog._field_linenos['nickname'] == 21


def test_enum_field_linenos():
    """Test that enum values have correct lineno information."""
    thrift = load('parser-cases/enums.thrift')

    assert hasattr(thrift.Lang, '_field_linenos')
    assert thrift.Lang._field_linenos['C'] == 2
    assert thrift.Lang._field_linenos['Go'] == 3
    assert thrift.Lang._field_linenos['Java'] == 4
    assert thrift.Lang._field_linenos['Javascript'] == 5
    assert thrift.Lang._field_linenos['PHP'] == 6
    assert thrift.Lang._field_linenos['Python'] == 7
    assert thrift.Lang._field_linenos['Ruby'] == 8

    assert hasattr(thrift.Country, '_field_linenos')
    assert thrift.Country._field_linenos['US'] == 13
    assert thrift.Country._field_linenos['UK'] == 14
    assert thrift.Country._field_linenos['CN'] == 15

    assert hasattr(thrift.OS, '_field_linenos')
    assert thrift.OS._field_linenos['OSX'] == 20
    assert thrift.OS._field_linenos['Win'] == 21
    assert thrift.OS._field_linenos['Linux'] == 22


def test_service_function_linenos():
    """Test that service functions have correct lineno information."""
    thrift = load('parser-cases/service.thrift')

    assert hasattr(thrift.EmailService, '_field_linenos')
    assert thrift.EmailService._field_linenos['ping'] == 17
    assert thrift.EmailService._field_linenos['send'] == 19
    assert thrift.EmailService._field_linenos['receive'] == 22
    assert thrift.EmailService._field_linenos['empty'] == 23


def test_type_linenos():
    """Test that types have correct lineno information."""
    thrift = load('parser-cases/service.thrift')

    assert hasattr(thrift.User, '__thrift_lineno__')
    assert thrift.User.__thrift_lineno__ == 1
    assert hasattr(thrift.User, '__thrift_file__')

    assert hasattr(thrift.NetworkError, '__thrift_lineno__')
    assert thrift.NetworkError.__thrift_lineno__ == 11
    assert hasattr(thrift.NetworkError, '__thrift_file__')

    assert hasattr(thrift.EmailService, '__thrift_lineno__')
    assert thrift.EmailService.__thrift_lineno__ == 16
    assert hasattr(thrift.EmailService, '__thrift_file__')


def test_include_file_path():
    """Test that included types have correct file path information."""
    thrift = load('parser-cases/include.thrift', include_dirs=[
        './parser-cases'], module_name='include_thrift')

    assert hasattr(thrift, '__thrift_file__')
    assert 'include.thrift' in thrift.__thrift_file__

    included_thrift = getattr(thrift, 'included')
    assert hasattr(included_thrift, '__thrift_file__')
    assert 'included.thrift' in included_thrift.__thrift_file__
