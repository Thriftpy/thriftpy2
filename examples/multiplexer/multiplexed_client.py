# -*- coding: utf-8 -*-

import thriftpy2
from thriftpy2.rpc import client_context
from thriftpy2.protocol import (
    TBinaryProtocolFactory,
    TMultiplexedProtocolFactory
    )

dd_thrift = thriftpy2.load("dingdong.thrift", module_name="dd_thrift")
pp_thrift = thriftpy2.load("pingpong.thrift", module_name="pp_thrift")

DD_SERVICE_NAME = "dd_thrift"
PP_SERVICE_NAME = "pp_thrift"


def main():
    binary_factory = TBinaryProtocolFactory()
    dd_factory = TMultiplexedProtocolFactory(binary_factory, DD_SERVICE_NAME)
    with client_context(dd_thrift.DingService, '127.0.0.1', 9090,
                        proto_factory=dd_factory) as c:
        # ring that doorbell
        dong = c.ding()
        print(dong)

    pp_factory = TMultiplexedProtocolFactory(binary_factory, PP_SERVICE_NAME)
    with client_context(pp_thrift.PingService, '127.0.0.1', 9090,
                        proto_factory=pp_factory) as c:
        # play table tennis like a champ
        pong = c.ping()
        print(pong)


if __name__ == '__main__':
    main()
