import socket
from typing import Dict


def extract_host_port_from_request(request: bytes) -> tuple[str, int]:
    host_string_start = request.find(b"Host: ") + len(b"Host: ")
    host_string_end = request.find(b"\r\n", host_string_start)
    host_string = request[host_string_start:host_string_end].decode("utf-8")

    webserver_pos = host_string.find("/")
    if webserver_pos == -1:
        webserver_pos = len(host_string)

    port_pos = host_string.find(":")
    if port_pos == -1 or webserver_pos < port_pos:
        port = 80
        host = host_string[:webserver_pos]
    else:
        port = int((host_string[(port_pos + 1) :])[: webserver_pos - port_pos - 1])
        host = host_string[:port_pos]

    return host, port


def parse_headers_from_request(request: bytes) -> Dict[str, str]:
    try:
        header_bytes = request.split(b"\r\n\r\n", 1)[0]
        lines = header_bytes.split(b"\r\n")
        headers: Dict[str, str] = {}
        for line in lines[1:]:
            if b":" in line:
                name, value = line.split(b":", 1)
                headers[name.decode("utf-8").strip().title()] = value.decode("utf-8").strip()
        return headers
    except Exception:
        return {}


def send_proxy_auth_required(client: socket.socket) -> None:
    body = b"Proxy Authentication Required"
    response = (
        b"HTTP/1.1 407 Proxy Authentication Required\r\n"
        b'Proxy-Authenticate: Basic realm="Proxy"\r\n'
        b"Content-Type: text/plain; charset=utf-8\r\n"
        b"Connection: close\r\n" + f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8") + body
    )
    try:
        client.sendall(response)
    except Exception:
        pass


def strip_proxy_authorization_header(request: bytes) -> bytes:
    try:
        header_part, sep, body = request.partition(b"\r\n\r\n")
        lines = header_part.split(b"\r\n")
        filtered = [lines[0]] + [
            ln for ln in lines[1:] if not ln.lower().startswith(b"proxy-authorization:")
        ]
        return b"\r\n".join(filtered) + sep + body
    except Exception:
        return request


def ensure_connection_close_header(request: bytes) -> bytes:
    """
    Ensure the outgoing request uses Connection: close and removes Proxy-Connection.

    - Sets/overrides `Connection: close`
    - Removes `Proxy-Connection`
    """
    try:
        header_part, sep, body = request.partition(b"\r\n\r\n")
        if not sep:
            return request

        lines = header_part.split(b"\r\n")
        if not lines:
            return request

        request_line = lines[0]

        new_headers: list[bytes] = []

        for line in lines[1:]:
            lower = line.lower()
            if lower.startswith(b"proxy-connection:"):
                continue
            if lower.startswith(b"connection:"):
                continue
            new_headers.append(line)

        # Force Connection: close
        new_headers.append(b"Connection: close")

        rebuilt = b"\r\n".join([request_line] + new_headers) + sep + body
        return rebuilt
    except Exception:
        return request


def get_method_and_target_from_request(request: bytes) -> tuple[str, str]:
    try:
        request_line = request.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        parts = request_line.split(" ")
        method = parts[0].upper() if parts else ""
        target = parts[1] if len(parts) > 1 else ""
        return method, target
    except Exception:
        return "", ""
