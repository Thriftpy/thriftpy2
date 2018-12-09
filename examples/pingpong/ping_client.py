# -*- coding: utf-8 -*-

import thriftpy2

from thriftpy2.rpc import client_context

pp_thrift = thriftpy2.load("pingpong.thrift", module_name="pp_thrift")


def main():
    with client_context(pp_thrift.PingService, '127.0.0.1', 6000) as c:
        pong = c.ping()
        print(pong)


if __name__ == '__main__':
    main()
