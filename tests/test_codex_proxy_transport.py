"""Actual framed I/O: the isolated probe must not confuse proxy bytes with JSONL."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import socket
import struct
import threading
from types import SimpleNamespace


def test_fragmented_message_ping_and_masked_client_request():
    path = Path(__file__).resolve().parents[1] / 'research/agent-memory-2026-10-06/pilots/codex_proxy_transport.py'
    spec = importlib.util.spec_from_file_location('probe_proxy', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client, server = socket.socketpair()
    client.settimeout(2)
    server.settimeout(2)
    observed = []
    def serve():
        with server:
            stream = server.makefile('rb', buffering=0)
            header = b''
            while not header.endswith(b'\r\n\r\n'):
                header += stream.read(1)
            key = next(line.split(b': ', 1)[1] for line in header.split(b'\r\n')
                       if line.startswith(b'Sec-WebSocket-Key:'))
            accept = base64.b64encode(hashlib.sha1(key + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest())
            server.sendall(b'HTTP/1.1 101 Switching Protocols\r\nSec-WebSocket-Accept: ' + accept + b'\r\n\r\n')
            head = stream.read(2)
            size = head[1] & 127
            if size == 126:
                size = struct.unpack('!H', stream.read(2))[0]
            mask = stream.read(4)
            body = stream.read(size)
            observed.append(bytes(c ^ mask[i % 4] for i, c in enumerate(body)))
            # Fragmented JSON with an interleaved ping.
            server.sendall(b'\x01\x06{"id":' + b'\x89\x01x' + b'\x80\x027}')
            pong_head = stream.read(2)
            pong_mask = stream.read(4)
            pong = stream.read(pong_head[1] & 127)
            observed.append((pong_head[0] & 15, bytes(c ^ pong_mask[i % 4] for i, c in enumerate(pong))))
    worker = threading.Thread(target=serve)
    worker.start()
    proc = SimpleNamespace(stdin=client.makefile('wb', buffering=0), stdout=client.makefile('rb', buffering=0))
    transport = module.ProxyTransport(proc)
    try:
        transport.send({'id':7, 'text':'a' * 200})
        assert transport.receive(2) == {'id':7}
        worker.join(2)
        assert not worker.is_alive()
        assert b'"id": 7' in observed[0]
        assert observed[1] == (10, b'x')
    finally:
        transport.close()
        proc.stdin.close()
        proc.stdout.close()
        client.close()
