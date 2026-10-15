"""Process-local egress guard; does not change Windows or firewall settings."""
import socket

_installed = False


def disable_outbound_connections():
    global _installed
    if _installed:
        return
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def external(sock, address):
        # Windows asyncio creates a loopback socket pair for its event loop.
        return sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ('127.0.0.1', '::1')

    def connect(sock, address):
        if external(sock, address):
            raise OSError('本地PDF识别进程不允许建立外部连接。')
        return original_connect(sock, address)

    def connect_ex(sock, address):
        if external(sock, address):
            return 10013
        return original_connect_ex(sock, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    _installed = True
