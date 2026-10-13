"""Bounded WebSocket-over-stdio transport for an explicitly selected test proxy.

Uses the same protocol as Telecodex's native proxy. The caller owns and isolates
the process and socket; this module never selects the production daemon.
"""
import base64
import hashlib
import json
import os
import selectors
import struct
import time


class ProxyTransport:
    def __init__(self, process):
        self.process = process
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ)
        key = base64.b64encode(os.urandom(16)).decode()
        process.stdin.write((
            'GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n'
            'Connection: Upgrade\r\nSec-WebSocket-Key: ' + key + '\r\n'
            'Sec-WebSocket-Version: 13\r\n\r\n').encode())
        process.stdin.flush()
        header = bytearray()
        deadline = time.monotonic() + 10
        while not header.endswith(b'\r\n\r\n'):
            header.extend(self.read(1, deadline))
            if len(header) > 8192:
                raise ValueError('oversized proxy handshake')
        expected = base64.b64encode(hashlib.sha1(
            (key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101 ') or expected not in header:
            raise ValueError('invalid proxy handshake')

    def read(self, size, deadline):
        while len(self.buffer) < size:
            if not self.selector.select(max(0, deadline - time.monotonic())):
                raise TimeoutError('proxy response timeout')
            data = os.read(self.process.stdout.fileno(), 65536)
            if not data:
                raise EOFError('isolated proxy closed')
            self.buffer.extend(data)
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def frame(self, data, opcode=1):
        mask = os.urandom(4)
        size = len(data)
        length = bytes([128 | size]) if size < 126 else (
            b'\xfe' + struct.pack('!H', size) if size < 65536 else
            b'\xff' + struct.pack('!Q', size))
        value = bytes([128 | opcode]) + length + mask
        value += bytes(c ^ mask[i % 4] for i, c in enumerate(data))
        self.process.stdin.write(value)
        self.process.stdin.flush()

    def send(self, value):
        self.frame(json.dumps(value).encode())

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        message = bytearray()
        while True:
            head = self.read(2, deadline)
            opcode, size = head[0] & 15, head[1] & 127
            if size == 126:
                size = struct.unpack('!H', self.read(2, deadline))[0]
            elif size == 127:
                size = struct.unpack('!Q', self.read(8, deadline))[0]
            if size > 64 * 1024 * 1024 or head[1] & 128:
                raise ValueError('unsupported proxy frame')
            data = self.read(size, deadline)
            if opcode == 8:
                raise EOFError('isolated proxy closed')
            if opcode in (9, 10):
                if opcode == 9:
                    self.frame(data, 10)
                continue
            if opcode not in (0, 1):
                raise ValueError('unexpected proxy opcode')
            message.extend(data)
            if len(message) > 64 * 1024 * 1024:
                raise ValueError('oversized proxy message')
            if head[0] & 128:
                return json.loads(message)

    def close(self):
        self.selector.close()
