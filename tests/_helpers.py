"""Helpers for tests that start real servers on sockets."""
import socket
import ssl
import time


def free_port(host="127.0.0.1"):
    """Ask the kernel for a currently unused TCP port on ``host``."""
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def wait_for_port(port, host="127.0.0.1", timeout=5.0, use_ssl=False):
    """Block until a server accepts TCP connections on ``host:port``.

    With ``use_ssl`` a TLS handshake is completed as well, so an SSL server
    does not see a bare TCP connect and log a failed handshake.
    """
    ctx = None
    if use_ssl:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1) as sock:
                if ctx is not None:
                    with ctx.wrap_socket(sock, server_hostname=host):
                        pass
                return
        except OSError:
            time.sleep(0.01)
    raise RuntimeError(
        "server did not start listening on %s:%d" % (host, port))


def wait_for_unix_socket(path, timeout=5.0):
    """Block until a server accepts connections on the unix socket ``path``."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(path)
                return
        except OSError:
            time.sleep(0.01)
    raise RuntimeError("server did not start listening on %s" % path)


def bound_port(get_sock, timeout=5.0):
    """Return the port of the socket ``get_sock()`` yields once it is bound.

    Meant for servers started with ``port=0`` in a thread: ``get_sock`` is
    polled until it returns a socket that the kernel has assigned a port to.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        sock = get_sock()
        if sock is not None:
            port = sock.getsockname()[1]
            if port:
                return port
        time.sleep(0.01)
    raise RuntimeError("server socket was not bound in time")
