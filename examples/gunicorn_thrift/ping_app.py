# -*- coding: utf-8 -*-

import thriftpy2
from thriftpy2.thrift import TProcessor

pingpong = thriftpy2.load("pingpong.thrift")


class Dispatcher(object):
    def ping(self):
        print("ping pong!")
        return 'pong'

app = TProcessor(pingpong.PingService, Dispatcher())
