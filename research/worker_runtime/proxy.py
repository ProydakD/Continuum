"""Codex-facing stdio MCP transport. No database or host file access."""
import os
import socket
import sys
import threading

MAX_LINE = 262144
sock = socket.create_connection(("127.0.0.1", int(os.environ["CONTINUUM_BRIDGE_PORT"])), timeout=20)
sock.settimeout(None)
stream = sock.makefile("rb")


def read_responses():
    while line := stream.readline(MAX_LINE + 1):
        if len(line) > MAX_LINE:
            os._exit(2)
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()


threading.Thread(target=read_responses, daemon=True).start()
while line := sys.stdin.buffer.readline(MAX_LINE + 1):
    if len(line) > MAX_LINE:
        sys.exit(2)
    sock.sendall(line)
