# -*- coding: utf-8 -*-

import thriftpy2
from thriftpy2.rpc import client_context

pingpong = thriftpy2.load("pingpong.thrift")


def main():
    with client_context(pingpong.PingService, '127.0.0.1', 8000) as c:
        pong = c.ping()
        print(pong)


if __name__ == '__main__':
    main()
