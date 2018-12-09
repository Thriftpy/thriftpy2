# -*- coding: utf-8 -*-

import thriftpy2
from thriftpy2.protocol import TBinaryProtocolFactory
from thriftpy2.server import TThreadedServer
from thriftpy2.thrift import TProcessor, TMultiplexedProcessor
from thriftpy2.transport import TBufferedTransportFactory, TServerSocket


dd_thrift = thriftpy2.load("dingdong.thrift", module_name="dd_thrift")
pp_thrift = thriftpy2.load("pingpong.thrift", module_name="pp_thrift")

DD_SERVICE_NAME = "dd_thrift"
PP_SERVICE_NAME = "pp_thrift"


class DingDispatcher(object):
    def ding(self):
        print("ding dong!")
        return 'dong'


class PingDispatcher(object):
    def ping(self):
        print("ping pong!")
        return 'pong'


def main():
    dd_proc = TProcessor(dd_thrift.DingService, DingDispatcher())
    pp_proc = TProcessor(pp_thrift.PingService, PingDispatcher())

    mux_proc = TMultiplexedProcessor()
    mux_proc.register_processor(DD_SERVICE_NAME, dd_proc)
    mux_proc.register_processor(PP_SERVICE_NAME, pp_proc)

    server = TThreadedServer(mux_proc, TServerSocket(),
                             iprot_factory=TBinaryProtocolFactory(),
                             itrans_factory=TBufferedTransportFactory())
    server.serve()


if __name__ == '__main__':
    main()
