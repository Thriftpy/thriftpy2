# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.
#
""" Async SASL transports for Thrift. """

# Async counterpart of thriftpy2.transport.sasl.TSaslClientTransport.

import struct
from io import BytesIO

from thriftpy2.transport import TTransportException

from .base import TAsyncTransportBase, readall


class TAsyncSaslClientTransport(TAsyncTransportBase):
    START = 1
    OK = 2
    BAD = 3
    ERROR = 4
    COMPLETE = 5

    def __init__(self, sasl_client_factory, mechanism, trans):
        """
        @param sasl_client_factory: a callable that returns a new sasl.Client object
        @param mechanism: the SASL mechanism (e.g. "GSSAPI")
        @param trans: the underlying transport over which to communicate.
        """
        self._trans = trans
        self.sasl_client_factory = sasl_client_factory
        self.sasl = None
        self.mechanism = mechanism
        self._wbuf = BytesIO()
        self._rbuf = BytesIO(b'')
        self.encode = None

    def is_open(self):
        return self._trans.is_open()

    async def open(self):
        if not self.is_open():
            await self._trans.open()

        if self.sasl is not None:
            raise TTransportException(
                type=TTransportException.ALREADY_OPEN,
                message="Already open!")
        self.sasl = self.sasl_client_factory()

        ret, chosen_mech, initial_response = self.sasl.start(self.mechanism)
        if not ret:
            raise TTransportException(type=TTransportException.NOT_OPEN,
                                      message=("Could not start SASL: %s" % self.sasl.getError()))

        # Send initial response
        await self._send_message(self.START, chosen_mech)
        await self._send_message(self.OK, initial_response)

        # SASL negotiation loop
        while True:
            status, payload = await self._recv_sasl_message()
            if status not in (self.OK, self.COMPLETE):
                raise TTransportException(type=TTransportException.NOT_OPEN,
                                          message=("Bad status: %d (%s)" % (status, payload)))
            if status == self.COMPLETE:
                break
            ret, response = self.sasl.step(payload)
            if not ret:
                raise TTransportException(type=TTransportException.NOT_OPEN,
                                          message=("Bad SASL result: %s" % (self.sasl.getError())))
            await self._send_message(self.OK, response)

    async def _send_message(self, status, body):
        # Depending on the SASL library, the mechanism name and the initial
        # response may come back as str or None instead of bytes.
        if body is None:
            body = b""
        elif isinstance(body, str):
            body = body.encode("utf-8")
        header = struct.pack(">BI", status, len(body))
        self._trans.write(header + body)
        await self._trans.flush()

    async def _recv_sasl_message(self):
        header = await readall(self._trans.read, 5)
        status, length = struct.unpack(">BI", header)
        if length > 0:
            payload = await readall(self._trans.read, length)
        else:
            payload = b""
        return status, payload

    def write(self, buf):
        self._wbuf.write(buf)

    async def flush(self):
        buffer = self._wbuf.getvalue()
        sasl = self.sasl
        assert sasl is not None
        # The first time we flush data, we send it to sasl.encode()
        # If the length doesn't change, then we must be using a QOP
        # of auth and we should no longer call sasl.encode(), otherwise
        # we encode every time.
        if self.encode is None:
            success, encoded = sasl.encode(buffer)
            if not success:
                raise TTransportException(type=TTransportException.UNKNOWN,
                                          message=sasl.getError())
            if (len(encoded) == len(buffer)):
                self.encode = False
                self._flush_plain(buffer)
            else:
                self.encode = True
                self._trans.write(encoded)
        elif self.encode:
            self._flush_encoded(buffer)
        else:
            self._flush_plain(buffer)

        await self._trans.flush()
        self._wbuf = BytesIO()

    def _flush_encoded(self, buffer):
        # sasl.encode() does the encoding and adds the length header, so nothing
        # to do but call it and write the result.
        sasl = self.sasl
        assert sasl is not None
        success, encoded = sasl.encode(buffer)
        if not success:
            raise TTransportException(type=TTransportException.UNKNOWN,
                                      message=sasl.getError())
        self._trans.write(encoded)

    def _flush_plain(self, buffer):
        # With QOP auth, sasl.encode() passes data through without adding a
        # length header, so we frame it ourselves.
        self._trans.write(struct.pack(">I", len(buffer)) + buffer)

    async def read(self, sz):
        ret = self._rbuf.read(sz)
        # A thrift message may span multiple SASL frames, so keep reading
        # frames until we have the requested amount of data. The protocol
        # layer calls read() directly and relies on getting exactly `sz`
        # bytes (see TAsyncTransportBase.read).
        while len(ret) < sz:
            await self._read_frame()
            chunk = self._rbuf.read(sz - len(ret))
            if not chunk:
                # A frame that yields no data (e.g. a zero-length frame or an
                # empty SASL decode result) would make this loop spin forever
                # without ever satisfying the request, so treat it as EOF.
                raise TTransportException(
                    type=TTransportException.END_OF_FILE,
                    message="Received empty SASL frame while more data expected")
            ret += chunk
        return ret

    async def _read_frame(self):
        header = await readall(self._trans.read, 4)
        (length,) = struct.unpack(">I", header)
        if self.encode:
            sasl = self.sasl
            assert sasl is not None
            # If the frames are encoded (i.e. you're using a QOP of auth-int or
            # auth-conf), then make sure to include the header in the bytes you send to
            # sasl.decode()
            encoded = header + await readall(self._trans.read, length)
            success, decoded = sasl.decode(encoded)
            if not success:
                raise TTransportException(type=TTransportException.UNKNOWN,
                                          message=sasl.getError())
        else:
            # If the frames are not encoded, just pass it through
            decoded = await readall(self._trans.read, length)
        self._rbuf = BytesIO(decoded)

    def close(self):
        self._trans.close()
        self.sasl = None
        self.encode = None
        self._wbuf = BytesIO()
        self._rbuf = BytesIO(b'')


class TAsyncSaslClientTransportFactory(object):
    def __init__(self, sasl_client_factory, mechanism):
        """
        @param sasl_client_factory: a callable that returns a new sasl.Client object
        @param mechanism: the SASL mechanism (e.g. "GSSAPI")
        """
        self.sasl_client_factory = sasl_client_factory
        self.mechanism = mechanism

    def get_transport(self, trans):
        return TAsyncSaslClientTransport(
            self.sasl_client_factory, self.mechanism, trans)
