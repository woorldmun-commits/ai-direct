"""Accept a visitor IP only when the trusted frontend signs it; forwarded headers alone are ignored."""
import hashlib
import hmac
import ipaddress
import time


def verified_client(headers, method, path, key):
    if not key:
        return None
    values = [v for n,v in headers if n == b'x-inrou-client']
    signatures = [v for n,v in headers if n == b'x-inrou-proxy-signature']
    if len(values) != 1 or len(signatures) != 1:
        return None
    try:
        value = values[0].decode('ascii')
        stamp, ip = value.split(':',1)
        if abs(time.time()-int(stamp)) > 60:
            return None
        ip = str(ipaddress.ip_address(ip))
        message = f'{method}\n{path}\n{value}'.encode()
        expected = hmac.new(key.encode(),message,hashlib.sha256).hexdigest().encode()
        return ip if hmac.compare_digest(expected,signatures[0]) else None
    except (ValueError, UnicodeError):
        return None
