# -*- coding: utf-8 -*-

from thriftpy.parser import load


def test_constants():
    thrift = load('parser-cases/recursive_definition.thrift')
    assert thrift.Bar.thrift_spec == {1: (12, 'test', thrift.Foo, False)}
    assert thrift.Foo.thrift_spec == {
        1: (12, 'test', thrift.Bar, False), 2: (8, 'some', False)}
