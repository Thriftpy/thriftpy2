# -*- coding: utf-8 -*-
import functools
from thriftpy2.thrift import args_to_kwargs
from thriftpy2.thrift import TApplicationException, TMessageType


class TAsyncClient:

    def __init__(self, service, iprot, oprot=None):
        self._service = service
        self._iprot = self._oprot = iprot
        if oprot is not None:
            self._oprot = oprot
        self._seqid = 0

    def __getattr__(self, _api):
        if _api in self._service.thrift_services:
            return functools.partial(self._req, _api)

        raise AttributeError("{} instance has no attribute '{}'".format(
            self.__class__.__name__, _api))

    def __dir__(self):
        return self._service.thrift_services

    async def _req(self, _api, *args, **kwargs):
        try:
            service_args = getattr(self._service, _api + "_args")
            kwargs = args_to_kwargs(service_args.thrift_spec, *args, **kwargs)
        except ValueError as e:
            raise TApplicationException(
                TApplicationException.UNKNOWN_METHOD,
                'missing required argument {arg} for {service}.{api}'.format(
                    arg=e.args[0], service=self._service.__name__, api=_api))
        result_cls = getattr(self._service, _api + "_result")

        await self._send(_api, **kwargs)
        # wait result only if non-oneway
        if not getattr(result_cls, "oneway"):
            return await self._recv(_api)

    async def _send(self, _api, **kwargs):
        oneway = getattr(getattr(self._service, _api + "_result"), "oneway")
        msg_type = TMessageType.ONEWAY if oneway else TMessageType.CALL
        self._oprot.write_message_begin(_api, msg_type, self._seqid)
        args = getattr(self._service, _api + "_args")()
        for k, v in kwargs.items():
            setattr(args, k, v)
        self._oprot.write_struct(args)
        self._oprot.write_message_end()
        await self._oprot.trans.flush()

    async def _recv(self, _api):
        fname, mtype, rseqid = await self._iprot.read_message_begin()
        if mtype == TMessageType.EXCEPTION:
            x = TApplicationException()
            await self._iprot.read_struct(x)
            await self._iprot.read_message_end()
            raise x
        result = getattr(self._service, _api + "_result")()
        await self._iprot.read_struct(result)
        await self._iprot.read_message_end()

        if hasattr(result, "success") and result.success is not None:
            return result.success

        # void api without throws
        if len(result.thrift_spec) == 0:
            return

        # check throws
        for k, v in result.__dict__.items():
            if k != "success" and v:
                raise v

        # no throws & not void api
        if hasattr(result, "success"):
            raise TApplicationException(TApplicationException.MISSING_RESULT)

    def close(self):
        self._iprot.trans.close()
        if self._iprot != self._oprot:
            self._oprot.trans.close()
