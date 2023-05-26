# -*- coding: utf-8 -*-
from thriftpy2.thrift import TApplicationException, TType, TMessageType


class TAsyncProcessor(object):

    def __init__(self, service, handler):
        self._service = service
        self._handler = handler

    async def process_in(self, iprot):
        api, type, seqid = await iprot.read_message_begin()
        if api not in self._service.thrift_services:
            await iprot.skip(TType.STRUCT)
            await iprot.read_message_end()
            return api, seqid, TApplicationException(TApplicationException.UNKNOWN_METHOD), None  # noqa

        args = getattr(self._service, api + "_args")()
        await iprot.read_struct(args)
        await iprot.read_message_end()
        result = getattr(self._service, api + "_result")()

        # convert kwargs to args
        api_args = [args.thrift_spec[k][1] for k in sorted(args.thrift_spec)]

        async def call():
            f = getattr(self._handler, api)
            return await f(*(args.__dict__[k] for k in api_args))

        return api, seqid, result, call

    async def send_exception(self, oprot, api, exc, seqid):
        oprot.write_message_begin(api, TMessageType.EXCEPTION, seqid)
        exc.write(oprot)
        oprot.write_message_end()
        await oprot.trans.flush()

    async def send_result(self, oprot, api, result, seqid):
        oprot.write_message_begin(api, TMessageType.REPLY, seqid)
        oprot.write_struct(result)
        oprot.write_message_end()
        await oprot.trans.flush()

    def handle_exception(self, e, result):
        for k in sorted(result.thrift_spec):
            if result.thrift_spec[k][1] == "success":
                continue

            _, exc_name, exc_cls, _ = result.thrift_spec[k]
            if isinstance(e, exc_cls):
                setattr(result, exc_name, e)
                return True
        return False

    async def process(self, iprot, oprot):
        api, seqid, result, call = await self.process_in(iprot)

        if isinstance(result, TApplicationException):
            return (await self.send_exception(oprot, api, result, seqid))

        try:
            result.success = await call()
        except Exception as e:
            # raise if api don't have throws
            if not self.handle_exception(e, result):
                raise

        if not result.oneway:
            await self.send_result(oprot, api, result, seqid)
