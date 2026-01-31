# -*- coding: utf-8 -*-
import asyncio
import thriftpy2

from thriftpy2.rpc import make_aio_server

echo_thrift = thriftpy2.load("echo.thrift", module_name="echo_thrift")


class Dispatcher(object):
    async def echo(self, param):
        print(param)
        await asyncio.sleep(0.1)
        return param


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    server = make_aio_server(
        echo_thrift.EchoService, Dispatcher(), '127.0.0.1', 6000,
        loop=loop)
    server.serve()


if __name__ == '__main__':
    main()
