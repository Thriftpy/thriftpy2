# -*- coding: utf-8 -*-

import thriftpy2

from thriftpy2.rpc import make_server

pp_thrift = thriftpy2.load("pingpong.thrift", module_name="pp_thrift")


class Dispatcher(object):
    def ping(self):
        print("ping pong!")
        return 'pong'


def main():
    server = make_server(pp_thrift.PingService, Dispatcher(),
                         '127.0.0.1', 6000)
    print("serving...")
    server.serve()


if __name__ == '__main__':
    main()
