import base64
import logging
import socket
import threading
from socket import socket as SocketType
from typing import Dict, Optional

from utils import (
    extract_host_port_from_request,
    parse_headers_from_request,
    send_proxy_auth_required,
    strip_proxy_authorization_header,
)

logger = logging.getLogger(__name__)

# logging.basicConfig()


class ProxyAuth:
    """
    Proxy authentication
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def authenticate(self, username: str, password: str) -> bool:
        """
        Authenticate the user and password
        """
        if not username or not password:
            return False

        if self.username == username and self.password == password:
            return True
        else:
            return False


class Proxy:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        connections: int = 10,
        production_mode: bool = True,
        auth: Optional[ProxyAuth] = None,
    ):
        """
        Proxy server
        """
        self.host = host
        self.port = port
        self.connections = connections
        self.production_mode = production_mode
        self.auth = auth

    def run(self) -> None:
        logging.info("Starting proxy server...")
        threads = []
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((self.host, self.port))
            server.listen(self.connections)
            if not self.production_mode:
                server.settimeout(1.0)
        except Exception as e:
            logging.critical(f"Error starting proxy server ({str(e)})")
            return

        logging.info(f"Proxy server started ({self.host}:{self.port})")
        logging.info(f"Accepting ({self.connections}) simultaneous connections")

        try:
            while True:
                try:
                    client, address = server.accept()
                    logging.debug(f"Accepting connection from ({address[0]}:{address[1]})")

                    thread_client = threading.Thread(
                        target=self.handle_client_request,
                        args=(
                            client,
                            address,
                        ),
                    )
                    thread_client.start()
                    threads.append(thread_client)
                    threads = [t for t in threads if t.is_alive()]

                except socket.timeout:
                    if not self.production_mode:
                        continue
                    else:
                        raise
        except KeyboardInterrupt:
            logging.info("Proxy server stopped by Ctrl+C. Ending...")
        finally:
            server.close()
            for t in threads:
                t.join()

    def handle_client_request(self, client: SocketType, address: tuple[str, int]) -> None:
        logging.debug("Request accepted")

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
                headers = parse_headers_from_request(request)
                if not self.is_authorized(headers):
                    logging.info(
                        f"Connection refused ({address[0]}:{address[1]}), reauthentication required"
                    )
                    send_proxy_auth_required(client)
                    return

            logging.info(f"Forwarding request to ({address[0]}:{address[1]})")

            host, port = extract_host_port_from_request(request)
            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect((host, port))

            forward_request = strip_proxy_authorization_header(request)

            destination_socket.sendall(forward_request)

            logging.debug("Received response from destination:")

            while True:
                data = destination_socket.recv(1024)
                if not data:
                    break
                logging.debug(f"response: {data.decode('utf-8', errors='replace')}")
                client.sendall(data)

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
