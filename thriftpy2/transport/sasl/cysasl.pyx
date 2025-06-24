# cython: freethreading_compatible = True

import struct

from thriftpy2.transport.cybase cimport (
    TCyBuffer,
    CyTransportBase,
    DEFAULT_BUFFER
)

from ..base import readall
from .. import TTransportException

from libc.string cimport memcpy

DEF MIN_BUFFER_SIZE = 1024

cdef class TCySaslClientTransport(CyTransportBase):
    """sasl wrapper"""

    START = 1
    OK = 2
    BAD = 3
    ERROR = 4
    COMPLETE = 5

    cdef object sasl, sasl_client_factory
    cdef TCyBuffer __wbuf, __rbuf
    cdef bint opened, encode, encode_decided
    cdef str mechanism

    def __init__(self, sasl_client_factory, mechanism, trans):
        """
        @param sasl_client_factory: a callable that returns a new sasl.Client object
        @param mechanism: the SASL mechanism (e.g. "GSSAPI")
        @param trans: the underlying transport over which to communicate.
        """
        self.trans = trans
        self.sasl_client_factory = sasl_client_factory
        self.sasl = None
        self.mechanism = mechanism
        self.__wbuf = TCyBuffer(DEFAULT_BUFFER)
        self.__rbuf = TCyBuffer(DEFAULT_BUFFER)
        self.encode_decided = False
        self.encode = False

    def is_open(self):
        return self.trans.is_open()

    def open(self):
        if not self.is_open():
            self.trans.open()

        if self.sasl is not None:
            raise TTransportException(
                type=TTransportException.NOT_OPEN,
                message="Already open!")
        self.sasl = self.sasl_client_factory()

        ret, chosen_mech, initial_response = self.sasl.start(self.mechanism)
        if not ret:
            raise TTransportException(type=TTransportException.NOT_OPEN,
                message=("Could not start SASL: %s" % self.sasl.getError()))

        # Send initial response
        self._send_message(self.START, chosen_mech)
        self._send_message(self.OK, initial_response)

        # SASL negotiation loop
        while True:
            status, payload = self._recv_sasl_message()
            if status not in (self.OK, self.COMPLETE):
                raise TTransportException(type=TTransportException.NOT_OPEN,
                    message=("Bad status: %d (%s)" % (status, payload)))
            if status == self.COMPLETE:
                break
            ret, response = self.sasl.step(payload)
            if not ret:
                raise TTransportException(type=TTransportException.NOT_OPEN,
                    message=("Bad SASL result: %s" % (self.sasl.getError())))
            self._send_message(self.OK, response)

    def _send_message(self, status, body):
        header = struct.pack(">BI", status, len(body))
        self.trans.write(header + body)
        self.trans.flush()

    def _recv_sasl_message(self):
        header = readall(self.trans.read, 5)
        status, length = struct.unpack(">BI", header)
        if length > 0:
            payload = readall(self.trans.read, length)
        else:
            payload = ""
        return status, payload

    def write(self, bytes data):
        cdef int sz = len(data)
        return self.c_write(data, sz)

    cdef c_write(self, const char *data, int sz):
        cdef:
            int cap = self.__wbuf.buf_size - self.__wbuf.data_size
            int r

        if cap < sz:
            self.c_flush()

        r = self.__wbuf.write(sz, data)
        if r == -1:
            raise MemoryError("Write to buffer error")

    def flush(self):
        return self.c_flush()

    cdef c_flush(self):
        cdef bytes data
        if self.__wbuf.data_size > 0:
            data = self.__wbuf.buf[:self.__wbuf.data_size]
            # The first time we flush data, we send it to sasl.encode()
            # If the length doesn't change, then we must be using a QOP
            # of auth and we should no longer call sasl.encode(), otherwise
            # we encode every time.
            if not self.encode_decided:
                success, encoded = self.sasl.encode(data)
                if not success:
                    raise TTransportException(type=TTransportException.UNKNOWN,
                                              message=self.sasl.getError())
                if (len(encoded)==len(data)):
                    self.encode = False
                    self._flushPlain(data)
                else:
                    self.encode = True
                    self.trans.write(encoded)
                self.encode_decided = True
            elif self.encode:
                self._flushEncoded(data)
            else:
                self._flushPlain(data)

            self.trans.flush()
            self.__wbuf.clean()
        return("DUN FLUSHING IN SASL")

    def _flushEncoded(self, buffer):
        # sasl.ecnode() does the encoding and adds the length header, so nothing
        # to do but call it and write the result.
        success, encoded = self.sasl.encode(buffer)
        if not success:
             raise TTransportException(type=TTransportException.UNKNOWN,
                                       message=self.sasl.getError())
        self.trans.write(encoded)

    def _flushPlain(self, buffer):
        # When we have QOP of auth, sasl.encode() will pass the input to the output
        # but won't put a length header, so we have to do that.

        # Note stolen from TFramedTransport:
        # N.B.: Doing this string concatenation is WAY cheaper than making
        # two separate calls to the underlying socket object. Socket writes in
        # Python turn out to be REALLY expensive, but it seems to do a pretty
        # good job of managing string buffer operations without excessive copies
        self.trans.write(struct.pack(">I", len(buffer)) + buffer)

    def read(self, sz):
        return self.get_string(sz)

    cdef c_read(self, int sz, char* out):
        cdef bytes ret

        ret = b""

        if sz <= 0:
            return 0

        orig_sz = sz
        if self.__rbuf.data_size < sz:
            # Read what remains, then get more data plz
            ret += self.__rbuf.buf[:self.__rbuf.data_size]
            sz -= self.__rbuf.data_size
            self._read_frame()

        ret += self.__rbuf.buf[self.__rbuf.cur:self.__rbuf.cur + sz]
        self.__rbuf.cur += sz
        self.__rbuf.data_size -= sz

        memcpy(out, <char*>ret, orig_sz)

    def _read_frame(self):
        header = readall(self.trans.read, 4)
        (length,) = struct.unpack(">I", header)
        if self.encode_decided and self.encode:
            # If the frames are encoded (i.e. you're using a QOP of auth-int or
            # auth-conf), then make sure to include the header in the bytes you send to
            # sasl.decode()
            encoded = header + readall(self.trans.read, length)
            success, decoded = self.sasl.decode(encoded)
            if not success:
                raise TTransportException(type=TTransportException.UNKNOWN,
                                          message=self.sasl.getError())
        else:
            # If the frames are not encoded, just pass it through
            decoded = readall(self.trans.read, length)
        self.__rbuf = TCyBuffer(len(decoded)+1)  # just to be sure make room for an extra byte
        memcpy(self.__rbuf.buf, <char*>decoded, len(decoded))
        self.__rbuf.data_size = len(decoded)
        self.__rbuf.cur = 0

    def clean(self):
        self.__rbuf.clean()
        self.__wbuf.clean()

    def close(self):
        self.trans.close()
        self.sasl = None

