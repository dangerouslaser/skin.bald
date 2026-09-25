"""Development client for Kodi's local TCP JSON-RPC server (Services > Control).

Usage: python3 tools/kodi_rpc.py GUI.GetProperties '{"properties":["currentwindow"]}'
       python3 tools/kodi_rpc.py builtin 'ReloadSkin()'
"""
import json
import socket
import struct
import sys
import secrets


def builtin(action):
    """Send a builtin via the localhost EventServer; verify effects through JSON-RPC.

    Protocol: Kodi tools/EventClients/lib/python/xbmcclient.py (v2, HELO / ACTION).
    """
    token = secrets.randbits(32)
    payload = b"\x01" + action.encode("utf-8") + b"\0"
    if len(payload) > 992:
        raise ValueError("Builtin exceeds the single-packet event limit")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        for kind, data in ((1, b"Bald development\0" + bytes(11)), (10, payload)):
            header = struct.pack("!4sBBHIIHI10x", b"XBMC", 2, 0, kind, 1, 1, len(data), token)
            connection.sendto(header + data, ("127.0.0.1", 9777))


def call(method, params=None):
    request = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        request["params"] = params
    decoder = json.JSONDecoder()
    with socket.create_connection(("127.0.0.1", 9090), timeout=5) as connection:
        connection.sendall(json.dumps(request).encode("utf-8"))
        pending = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                raise RuntimeError("Kodi closed the connection before replying")
            pending += chunk
            try:
                data = pending.decode("utf-8")
            except UnicodeDecodeError:
                continue
            while data.strip():
                data = data.lstrip()
                try:
                    response, end = decoder.raw_decode(data)
                except ValueError:
                    break
                data = data[end:]
                if response.get("id") == 1:
                    if "error" in response:
                        raise RuntimeError(response["error"])
                    return response["result"]
            pending = data.encode("utf-8")


if __name__ == "__main__":
    if sys.argv[1] == "builtin":
        builtin(sys.argv[2])
    else:
        print(json.dumps(call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else None), indent=2))
