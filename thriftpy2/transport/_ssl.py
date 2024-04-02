# -*- coding: utf-8 -*-

"""
The codes in this ssl compat lib were inspired by urllib3.utils.ssl_ module.
"""

import ssl
from ssl import SSLContext

# Disable weak or insecure ciphers by default
# (OpenSSL's default setting is 'DEFAULT:!aNULL:!eNULL')
# Enable a better set of ciphers by default
# This list has been explicitly chosen to:
#   * Prefer cipher suites that offer perfect forward secrecy (DHE/ECDHE)
#   * Prefer ECDHE over DHE for better performance
#   * Prefer any AES-GCM over any AES-CBC for better performance and security
#   * Then Use HIGH cipher suites as a fallback
#   * Then Use 3DES as fallback which is secure but slow
#   * Disable NULL authentication, NULL encryption, and MD5 MACs for security
#     reasons
DEFAULT_CIPHERS = (
    'ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
    'DH+HIGH:ECDH+3DES:DH+3DES:RSA+AESGCM:RSA+AES:RSA+HIGH:RSA+3DES:!aNULL:'
    '!eNULL:!MD5'
)

# Restricted and more secure ciphers for the server side
# This list has been explicitly chosen to:
#   * Prefer cipher suites that offer perfect forward secrecy (DHE/ECDHE)
#   * Prefer ECDHE over DHE for better performance
#   * Prefer any AES-GCM over any AES-CBC for better performance and security
#   * Then Use HIGH cipher suites as a fallback
#   * Then Use 3DES as fallback which is secure but slow
#   * Disable NULL authentication, NULL encryption, MD5 MACs, DSS, and RC4 for
#     security reasons
RESTRICTED_SERVER_CIPHERS = (
    'ECDH+AESGCM:DH+AESGCM:ECDH+AES256:DH+AES256:ECDH+AES128:DH+AES:ECDH+HIGH:'
    'DH+HIGH:ECDH+3DES:DH+3DES:RSA+AESGCM:RSA+AES:RSA+HIGH:RSA+3DES:!aNULL:'
    '!eNULL:!MD5:!DSS:!RC4'
)


def create_thriftpy_context(server_side=False, ciphers=None):
    """
    The SSLContext has some default security options, you can disable them
    manually, for example::

        from thriftpy2.transport import _ssl
        import ssl
        context = _ssl.create_thriftpy_context()
        context.options &= ~ssl.OP_NO_SSLv3

    You can do the same to enable compression.
    """

    # server/client default options
    if server_side:
        context = SSLContext(ssl.PROTOCOL_TLS_SERVER)
    else:
        context = SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False

    if ciphers:
        context.set_ciphers(ciphers)

    return context
