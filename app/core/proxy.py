import base64
import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

from utils import (
    ensure_connection_close_header,
    extract_host_port_from_request,
    parse_headers_from_request,
    send_proxy_auth_required,
    strip_proxy_authorization_header,
)

from .auth import ProxyAuth
from .firewall import ProxyFirewall

logger = logging.getLogger(__name__)

# logging.basicConfig()


class Proxy:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        backlog: int = 10,
        max_connections: int = 50,
        production_mode: bool = True,
        auth: Optional[ProxyAuth] = None,
        firewall: Optional[ProxyFirewall] = None,
    ):
        """
        Proxy server

        args:
            host (str): host to bind
            port (int): port to listen
            backlog (int): backlog of connections simultaneous
            max_connections (int): maximum number of requests processed simultaneously
            production_mode (bool): production mode
            auth (ProxyAuth): authentication class
        """
        self.host = host
        self.port = port
        self.backlog = backlog
        self.max_connections = max_connections
        self.production_mode = production_mode
        self.auth = auth
        self.firewall = firewall

        if self.backlog < self.max_connections:
            raise ValueError(
                f"The backlog ({self.backlog}) cannot be smaller than max connections ({self.max_connections})"
            )

    def run(self) -> None:
        logging.info("Starting proxy server...")
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((self.host, self.port))
            server.listen(self.backlog)
            if not self.production_mode:
                server.settimeout(1.0)
        except Exception as e:
            logging.critical(f"Error starting proxy server ({str(e)})")
            return

        logging.info(f"Proxy server started (http://{self.host}:{self.port})")
        logging.info(
            f"Accepting ({self.max_connections}) simultaneous connections, backlog: {self.backlog}"
        )

        if not self.production_mode:
            logging.info("To stop the server use (Ctrl+C)\n")

        try:
            with ThreadPoolExecutor(max_workers=self.max_connections) as executor:
                try:
                    while True:
                        try:
                            client, address = server.accept()
                            logging.debug(f"Accepting connection from ({address[0]}:{address[1]})")
                            if self.firewall is not None:
                                if not self.firewall.verify(address[0]):
                                    logging.info(
                                        f"Connection refused ({address[0]}:{address[1]}), firewall blocked"
                                    )
                                    client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                                    client.close()
                                    continue

                            executor.submit(self.handle_client_request, client, address)

                        except socket.timeout:
                            if not self.production_mode:
                                continue
                            else:
                                raise
                except KeyboardInterrupt:
                    logging.info("Proxy server stopped by Ctrl+C. Ending...")
                    logging.info("Wait until all open connections are closed...")
                finally:
                    server.close()

        except KeyboardInterrupt:
            logging.info("Terminating all open connections")

    def handle_client_request(self, client: socket.socket, address: tuple[str, int]) -> None:
        logging.debug("Request accepted")

        # Avoid hanging threads on slow clients
        try:
            client.settimeout(15)
        except Exception:
            pass

        request = b""
        while b"\r\n\r\n" not in request:
            try:
                data = client.recv(1024)
                if not data:
                    break
                request += data
                # logging.debug(f"{data.decode(errors='replace')}")
            except Exception as e:
                logging.debug(f"Error receiving client data: {e}")
                break

        try:
            if self.auth is not None:
                if self.firewall is not None and self.firewall.is_no_auth_required(address[0]):
                    pass
                else:
                    headers = parse_headers_from_request(request)
                    if not self.is_authorized(headers):
                        logging.info(
                            f"Connection refused ({address[0]}:{address[1]}), reauthentication required"
                        )
                        send_proxy_auth_required(client)
                        return

            logging.info(f"Forwarding request to ({address[0]}:{address[1]})")

            # Parse headers for Content-Length
            headers_all = parse_headers_from_request(request)
            content_length = 0
            try:
                if "Content-Length" in headers_all:
                    content_length = int(headers_all.get("Content-Length", "0") or "0")
            except Exception:
                content_length = 0

            host, port = extract_host_port_from_request(request)
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect((host, port))
            try:
                destination_socket.settimeout(15)
            except Exception:
                pass

            forward_request = strip_proxy_authorization_header(request)
            forward_request = ensure_connection_close_header(forward_request)

            # If there is a body, ensure we forward it entirely based on Content-Length
            header_part, sep, body_initial = forward_request.partition(b"\r\n\r\n")
            sent_all = False
            if sep:
                # Send header + whatever body bytes we already have
                destination_socket.sendall(header_part + sep + body_initial)

                initial_body_len = len(body_initial)
                remaining = max(0, content_length - initial_body_len)

                while remaining > 0:
                    chunk = client.recv(min(4096, remaining))
                    if not chunk:
                        break
                    destination_socket.sendall(chunk)
                    remaining -= len(chunk)
                sent_all = True

            if not sent_all:
                # Fallback: send all as-is
                destination_socket.sendall(forward_request)

            logging.debug("Received response from destination:")

            while True:
                try:
                    data = destination_socket.recv(4096)
                    if not data:
                        break
                    logging.debug(f"response: {data.decode('utf-8', errors='replace')}")
                    client.sendall(data)
                except socket.timeout:
                    # Assume end of response on inactivity
                    break

            destination_socket.close()
        except Exception as e:
            logging.error(f"Error forwarding to destination: {e}")
        finally:
            client.close()

    def is_authorized(self, headers: Dict[str, str]) -> bool:
        auth_header = headers.get("Proxy-Authorization")
        if not auth_header:
            return False

        scheme, _, param = auth_header.partition(" ")
        if scheme.lower() != "basic" or not param:
            return False

        try:
            decoded = base64.b64decode(param).decode("utf-8")
            username, _, password = decoded.partition(":")
        except Exception:
            return False

        return self.auth.authenticate(username, password) if self.auth else False
