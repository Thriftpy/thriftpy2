# -*- coding: utf-8 -*-
import thriftpy2
import asyncio
from thriftpy2.rpc import make_aio_client


echo_thrift = thriftpy2.load("echo.thrift", module_name="echo_thrift")


async def main():
    client = await make_aio_client(
        echo_thrift.EchoService, '127.0.0.1', 6000)
    print(await client.echo('hello, world'))
    client.close()


if __name__ == '__main__':
    asyncio.run(main())
