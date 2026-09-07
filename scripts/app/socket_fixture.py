"""Test-only loopback listener; publish the OS-selected port after listen()."""
import socket
from pathlib import Path
import sys

with socket.socket() as server:
    server.bind(('127.0.0.1', 0))
    server.listen(8)
    Path(sys.argv[1]).write_text(str(server.getsockname()[1]))
    while True:
        connection, _ = server.accept()
        with connection:
            connection.sendall(b'ready\n')
