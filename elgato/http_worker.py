"""One bounded HTTP exchange, isolated so the caller can kill slow DNS/I/O.

Invoked as an isolated Python script. Input (including credentials) uses a pipe,
never argv, environment or logs. This worker has no device or desktop imports.
"""
import base64
import http.client
import ipaddress
import json
import os
import socket
import sys


def exchange(spec):
    host = spec['host']
    port = spec['port']
    mode = spec['mode']
    if mode == 'loopback':
        if host != '127.0.0.1' or port != 37890:
            raise ValueError('Invalid OpenXLR endpoint')
        addresses = [host]
    else:
        try:
            addresses = [str(ipaddress.ip_address(host))]
        except ValueError:
            addresses = []
            for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM):
                address = item[4][0]
                if len(item[4]) == 4 and item[4][3]:
                    address += '%' + str(item[4][3])
                if address not in addresses:
                    addresses.append(address)
            addresses = sorted(addresses, key=lambda value: ipaddress.ip_address(value).version)[:8]
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_reserved:
                raise ValueError('Unsafe light address')
            if host.endswith('.local') and ip.is_global:
                raise ValueError('Local light name resolved outside the local network')
    if not addresses:
        raise ValueError('Device address unavailable')
    # Pin the resolved address. No second hostname lookup, proxies or redirects.
    connection = None
    for address in addresses:
        candidate = http.client.HTTPConnection(address, port, timeout=2)
        try:
            candidate.connect()
        except OSError:
            candidate.close()
            continue
        connection = candidate
        break
    if connection is None:
        raise OSError('Device connection failed')
    try:
        if mode == 'loopback':
            verify_local_peer(connection.sock)
        headers = dict(spec.get('headers', {}))
        headers['Host'] = (f'[{host}]' if ':' in host else host) + ':' + str(port)
        data = base64.b64decode(spec['data']) if spec.get('data') is not None else None
        connection.request(spec['method'], spec['path'], body=data, headers=headers)
        response = connection.getresponse()
        if 300 <= response.status < 400:
            raise ValueError('HTTP redirects are not allowed')
        if not 200 <= response.status < 300:
            raise ValueError('Device returned an HTTP error')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Compressed HTTP responses are not supported')
        size = response.getheader('Content-Length')
        if size is not None:
            if not size.isascii() or not size.isdecimal() or len(size) > 10:
                raise ValueError('Invalid HTTP content length')
            if int(size) > spec['limit']:
                raise ValueError('Device response is too large')
        body = response.read(spec['limit'] + 1)
        if len(body) > spec['limit']:
            raise ValueError('Device response is too large')
        if size is not None and len(body) != int(size):
            raise ValueError('Incomplete HTTP response')
        return body
    finally:
        connection.close()


def verify_local_peer(sock):
    """Reject a foreign user's established TCP peer before sending the token.

    Linux-specific: a listening-port check alone has a replacement race. Inspect
    the reverse established connection instead. Same-UID code remains trusted.
    """
    local = sock.getsockname()
    remote = sock.getpeername()
    def endpoint(value):
        address = socket.inet_aton(value[0])[::-1].hex().upper()
        return f'{address}:{value[1]:04X}'
    wanted_local, wanted_remote = endpoint(remote), endpoint(local)
    with open('/proc/net/tcp', encoding='ascii') as stream:
        for line in stream:
            fields = line.split()
            if len(fields) > 7 and fields[1:4] == [wanted_local, wanted_remote, '01']:
                if int(fields[7]) == os.getuid():
                    return
                break
    raise ValueError('OpenXLR peer is not owned by your user')


def main():
    try:
        raw = sys.stdin.buffer.read(16 * 1024 + 1)
        if len(raw) > 16 * 1024:
            raise ValueError('Request is too large')
        spec = json.loads(raw)
        body = exchange(spec)
        result = {'body': base64.b64encode(body).decode('ascii')}
    except ValueError as exc:
        result = {'error': str(exc)}
    except (OSError, http.client.HTTPException):
        result = {'error': 'Device is unavailable'}
    # Never print endpoint-provided errors, headers or input credentials.
    sys.stdout.write(json.dumps(result))


if __name__ == '__main__':
    main()
