# -*- coding: utf-8 -*-

import thriftpy2

from thriftpy2.protocol import TCyBinaryProtocolFactory
from thriftpy2.transport import TCyBufferedTransportFactory
from thriftpy2.rpc import client_context

calc_thrift = thriftpy2.load("calc.thrift", module_name="calc_thrift")


def main():
    with client_context(calc_thrift.Calculator, '127.0.0.1', 6000,
                        proto_factory=TCyBinaryProtocolFactory(),
                        trans_factory=TCyBufferedTransportFactory()) as cal:
        a = cal.mult(5, 2)
        b = cal.sub(7, 3)
        c = cal.sub(6, 4)
        d = cal.mult(b, 10)
        e = cal.add(a, d)
        f = cal.div(e, c)
        print(f)


if __name__ == '__main__':
    main()
