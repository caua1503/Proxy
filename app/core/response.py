import json
from http import HTTPStatus
from typing import Any, Literal, Optional


class ProxyResponse(bytes):
    def __new__(
        cls,
        status_code: int | HTTPStatus,
        body: Optional[Any] = None,
        headers: dict[str, str] = {},
        response_type: Optional[Literal["JSON", "BYTES", "TEXT"]] = None,
        reason: Optional[str] = None,
    ) -> "ProxyResponse":
        """
        Cria objeto ProxyResponse.

        Args:
            status_code (int | HTTPStatus): Código de status HTTP devolvido ao cliente.
            body (Any | None): Corpo da resposta: bytes, str ou JSON serializável.
            headers (dict[str, str]): Cabeçalhos opcionais da resposta.
            response_type (str | None): "JSON", "BYTES" ou "TEXT". Inferido pelo body se None.
            reason (str | None): Frase de motivo opcional enviada ao cliente.
        """
        reason = reason if reason else HTTPStatus(status_code).phrase

        default_type = None

        if body is None:
            body_bytes = b""
        elif isinstance(body, (bytes, bytearray, memoryview)):
            body_bytes = bytes(body)
            default_type = "BYTES"
        elif isinstance(body, (dict, list)):
            body_bytes = json.dumps(body).encode("utf-8")
            default_type = "JSON"
        else:
            body_bytes = str(body).encode("utf-8")
            default_type = "TEXT"

        inferred_type = response_type if response_type else default_type

        if inferred_type == "JSON":
            headers.setdefault("Content-Type", "application/json; charset=utf-8")
        elif inferred_type == "TEXT":
            headers.setdefault("Content-Type", "text/plain; charset=utf-8")
        elif inferred_type == "BYTES":
            headers.setdefault("Content-Type", "application/octet-stream")

        if body_bytes:
            headers["Content-Length"] = str(len(body_bytes))

        status_line = f"HTTP/1.1 {status_code} {reason}\r\n".encode("utf-8")
        header_lines = b"\r\n".join(
            f"{name}: {value}".encode("utf-8") for name, value in headers.items()
        )

        raw = status_line + header_lines + b"\r\n\r\n" + body_bytes

        obj = bytes.__new__(cls, raw)

        obj.status_code = status_code  # type: ignore[attr-defined]
        obj.headers = headers  # type: ignore[attr-defined]
        obj.body = body_bytes  # type: ignore[attr-defined]
        obj.response_type = inferred_type  # type: ignore[attr-defined]
        obj.reason = reason  # type: ignore[attr-defined]

        return obj


class ProxyProtocol:
    CONNECTION_ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"
    FINISHED = b"\r\n\r\n"
    CONNECTION_CLOSE = {"Connection": "close"}

    def CONNECT_LINE(target: str) -> bytes:
        return (f"CONNECT {target} HTTP/1.1\r\n\r\n").encode()
