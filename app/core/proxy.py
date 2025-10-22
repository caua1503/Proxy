import asyncio
import select
import socket
from asyncio.streams import StreamReader, StreamWriter
from concurrent.futures import ThreadPoolExecutor
from http import HTTPMethod, HTTPStatus
from typing import Optional

from utils import (
    ensure_connection_close_header,
    extract_host_port_from_request,
    get_content_length_from_request,
    get_method_and_target_from_request,
    parse_headers_from_request,
    strip_proxy_authorization_header,
)

from .auth import ProxyAuth
from .firewall import ProxyFirewall
from .logger import ProxyLogger, ProxyLogLevel
from .response import ProxyProtocol, ProxyResponse


class SyncProxy:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8888,
        backlog: int = 20,
        max_connections: int = 20,
        auth: Optional[ProxyAuth] = None,
        firewall: Optional[ProxyFirewall] = None,
        logger: ProxyLogger = ProxyLogger(),
        debug: bool = False,
        timeout: int = 30,
    ):
        """
        Proxy server

        args:
            host (str): host to bind
            port (int): port to listen
            backlog (int): backlog of connections simultaneous
            max_connections (int): maximum number of requests processed simultaneously
            auth (ProxyAuth): authentication class
            firewall (ProxyFirewall): firewall class
            logger (ProxyLogger): logger class
            debug (bool): debug mode
            timeout (int): timeout for the connection

        """
        self.host = host
        self.port = port
        self.backlog = backlog
        self.max_connections = max_connections
        self.debug = debug
        self.auth = auth
        self.firewall = firewall
        self.timeout = timeout
        self.logger = logger if not debug else ProxyLogger(level=ProxyLogLevel.DEBUG)

        if self.backlog < self.max_connections:
            self.logger.warning(
                f"The backlog ({self.backlog}) cannot be smaller than max connections ({self.max_connections})"  # noqa: E501
            )

    def run(self) -> None:
        self.logger.info("Starting proxy server...")
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.bind((self.host, self.port))
            server.listen(self.backlog)
            if self.debug:
                server.settimeout(1.0)
                self.logger.info("Debug mode enabled")
        except Exception as e:
            self.logger.critical(f"Error starting proxy server ({str(e)})")
            return

        self.logger.info(f"Proxy server started (http://{self.host}:{self.port})")
        self.logger.info(
            f"Accepting ({self.max_connections}) simultaneous connections, backlog: {self.backlog}"
        )

        if self.debug:
            self.logger.info("To stop the server use (Ctrl+C)\n")

        try:  # noqa: PLR1702
            with ThreadPoolExecutor(max_workers=self.max_connections) as executor:
                try:
                    while True:
                        try:
                            client, address = server.accept()
                            self.logger.debug(
                                f"Accepting connection from ({address[0]}:{address[1]})"
                            )
                            if self.firewall is not None:
                                if not self.firewall.verify(address[0]):
                                    self.logger.info(
                                        f"Connection refused ({address[0]}:{address[1]}) - (firewall blocked)"  # noqa: E501
                                    )
                                    client.sendall(
                                        ProxyResponse(
                                            HTTPStatus.FORBIDDEN, headers={"Connection": "close"}
                                        )
                                    )
                                    client.close()
                                    continue

                            executor.submit(self._handle_client_request, client, address)

                        except socket.timeout:
                            if self.debug:
                                continue
                            else:
                                raise
                except KeyboardInterrupt:
                    self.logger.info("Proxy server stopped by Ctrl+C. Ending...")
                    self.logger.info("Wait until all open connections are closed...")
                finally:
                    server.close()

        except KeyboardInterrupt:
            self.logger.info("Terminating all open connections")

    def _handle_client_request(self, client: socket.socket, address: tuple[str, int]) -> None:  # noqa: PLR0914, PLR0915, PLR0912
        self.logger.debug("Request accepted")

        try:
            client.settimeout(self.timeout)
        except Exception:
            pass

        request = b""
        while ProxyProtocol.FINISHED not in request:
            try:
                data = client.recv(1024)
                if not data:
                    break
                request += data
                # self.logger.debug(f"{data.decode(errors='replace')}")
            except Exception as e:
                self.logger.debug(f"Error receiving client data: {e}")
                break

        has_responded = False
        try:
            if self.auth is not None:
                if self.firewall is not None and self.firewall.is_no_auth_required(address[0]):
                    pass
                else:
                    headers = parse_headers_from_request(request)
                    if not self.auth.is_authorized(headers):
                        self.logger.info(
                            f"Connection refused ({address[0]}:{address[1]}) - (reauthentication required)"  # noqa: E501
                        )
                        client.sendall(
                            ProxyResponse(
                                HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
                                headers={"Connection": "close"},
                            )
                        )
                        return

            method, target = get_method_and_target_from_request(request)

            if method == HTTPMethod.CONNECT:
                host, _, port_str = target.partition(":")
                try:
                    port = int(port_str) if port_str else 443
                except Exception:
                    port = 443

                self.logger.debug(f"Tunneling request to ({host}:{port})")

                destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                destination_socket.connect((host, port))
                try:
                    destination_socket.settimeout(self.timeout)
                except Exception:
                    pass

                client.sendall(ProxyProtocol.CONNECTION_ESTABLISHED)
                has_responded = True
                self._tunnel(client, destination_socket)
                return

            self.logger.info(f"Forwarding request to ({address[0]}:{address[1]})")

            content_length = get_content_length_from_request(request)

            host, port = extract_host_port_from_request(request)

            if not host or not host.strip():
                self.logger.error("Invalid or empty host extracted from request")
                client.sendall(
                    ProxyResponse(HTTPStatus.BAD_REQUEST, headers={"Connection": "close"})
                )
                return

            destination_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            destination_socket.connect((host, port))
            try:
                destination_socket.settimeout(self.timeout)
            except Exception:
                pass

            forward_request = strip_proxy_authorization_header(request)
            forward_request = ensure_connection_close_header(forward_request)

            header_part, sep, body_initial = forward_request.partition(ProxyProtocol.FINISHED)
            sent_all = False
            if sep:
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
                destination_socket.sendall(forward_request)

            self.logger.debug("Received response from destination:")

            while True:
                try:
                    data = destination_socket.recv(4096)
                    if not data:
                        break
                    self.logger.debug(f"response: {data.decode('utf-8', errors='replace')}")
                    client.sendall(data)
                    if not has_responded:
                        has_responded = True
                except socket.timeout:
                    break

            destination_socket.close()
        except Exception as e:
            self.logger.error(f"Error forwarding to destination: {e}")
            if not has_responded:
                client.sendall(
                    ProxyResponse(HTTPStatus.BAD_GATEWAY, headers={"Connection": "close"})
                )
        finally:
            client.close()

    def _tunnel(self, client: socket.socket, destination_socket: socket.socket) -> None:  # noqa: PLR0913
        try:
            sockets = [client, destination_socket]
            while True:
                readable, _, _ = select.select(sockets, [], [], self.timeout)
                if not readable:
                    continue
                for s in readable:
                    other = destination_socket if s is client else client
                    try:
                        data = s.recv(4096)
                        if not data:
                            return
                        other.sendall(data)
                    except Exception:
                        return
        finally:
            try:
                destination_socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                destination_socket.close()
            except Exception:
                pass


class Proxy:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8888,
        backlog: int = 1000,
        max_connections: int = 1000,
        auth: Optional[ProxyAuth] = None,
        firewall: Optional[ProxyFirewall] = None,
        logger: ProxyLogger = ProxyLogger(),
        debug: bool = False,
        timeout: int = 30,
    ):
        """
        Proxy server

        args:
            host (str): host to bind
            port (int): port to listen
            backlog (int): backlog of connections simultaneous
            max_connections (int): maximum number of requests processed simultaneously
            auth (ProxyAuth): authentication class
            firewall (ProxyFirewall): firewall class
            logger (ProxyLogger): logger class
            debug (bool): debug mode
            timeout (int): timeout for the connection

        """
        self.host = host
        self.port = port
        self.backlog = backlog
        self.max_connections = max_connections
        self.debug = debug
        self.auth = auth
        self.firewall = firewall
        self.timeout = timeout
        self.logger = logger if not debug else ProxyLogger(level=ProxyLogLevel.DEBUG)

        if self.backlog < self.max_connections:
            self.logger.warning(
                f"The backlog ({self.backlog}) cannot be smaller than max connections ({self.max_connections})"  # noqa: E501
            )

    def get_info(self) -> tuple[str, int, ProxyAuth]:
        return self.host, self.port, self.auth

    async def _run(self) -> None:
        self.logger.info("Starting async proxy server...")
        self._semaphore = asyncio.Semaphore(self.max_connections)

        try:
            server = await asyncio.start_server(
                self._handle_client_request,
                self.host,
                self.port,
                backlog=self.backlog,
            )
        except Exception as e:
            self.logger.critical(f"Error starting async proxy server ({str(e)})")
            return
        self.logger.info(f"Proxy server started (http://{self.host}:{self.port})")
        self.logger.info(
            f"Accepting ({self.max_connections}) simultaneous connections, backlog: {self.backlog}"
        )
        if self.debug:
            self.logger.info("Debug mode enabled")

        async with server:
            try:
                await server.serve_forever()
            except asyncio.CancelledError:
                pass

    def run(self) -> None:
        asyncio.run(self._run())

    async def async_run(self) -> None:
        return await self._run()

    async def _handle_client_request(self, client: StreamReader, writer: StreamWriter) -> None:  # noqa: PLR0915, PLR0912, PLR0914, PLR0911
        PEER_TUPLE_MIN_LEN_FOR_PORT = 2
        async with self._semaphore:  # type: ignore[attr-defined] # noqa: PLR1702, PLR0914
            peer = writer.get_extra_info("peername")
            client_host = peer[0] if isinstance(peer, tuple) and len(peer) >= 1 else "?"
            client_port = (
                peer[1]
                if isinstance(peer, tuple) and len(peer) >= PEER_TUPLE_MIN_LEN_FOR_PORT
                else -1
            )

            self.logger.debug("Request accepted")

            if self.firewall is not None and not self.firewall.verify(client_host):
                self.logger.info(
                    f"Connection refused ({client_host}:{client_port}) - (firewall blocked)"
                )
                try:
                    writer.write(
                        ProxyResponse(HTTPStatus.FORBIDDEN, headers={"Connection": "close"})
                    )
                    await writer.drain()
                finally:
                    writer.close()
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
                return

            request = b""
            try:
                while ProxyProtocol.FINISHED not in request:
                    data = await asyncio.wait_for(client.read(1024), timeout=self.timeout)
                    if not data:
                        break
                    request += data
            except asyncio.TimeoutError:
                self.logger.debug("Timeout receiving client headers/body")
                try:
                    writer.write(
                        ProxyResponse(HTTPStatus.REQUEST_TIMEOUT, headers={"Connection": "close"})
                    )
                    await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                except Exception:
                    pass
                return
            except Exception as e:
                self.logger.debug(f"Error receiving client data: {e}")

            has_responded = False
            try:
                if self.auth is not None:
                    if self.firewall is not None and self.firewall.is_no_auth_required(client_host):
                        pass
                    else:
                        headers = parse_headers_from_request(request)
                        if not self.auth.is_authorized(headers):
                            self.logger.info(
                                f"Connection refused ({client_host}:{client_port}) - (reauthentication required)"  # noqa: E501
                            )
                            writer.write(
                                ProxyResponse(
                                    HTTPStatus.PROXY_AUTHENTICATION_REQUIRED,
                                    headers={"Connection": "close"},
                                )
                            )
                            await writer.drain()
                            return

                method, target = get_method_and_target_from_request(request)

                if method == HTTPMethod.CONNECT:
                    host, _, port_str = target.partition(":")
                    try:
                        port = int(port_str) if port_str else 443
                    except Exception:
                        port = 443

                    self.logger.debug(f"Tunneling request to ({host}:{port})")

                    try:
                        dest_reader, dest_writer = await asyncio.wait_for(
                            asyncio.open_connection(host, port), timeout=self.timeout
                        )
                    except Exception as e:
                        self.logger.error(f"Error connecting to destination {host}:{port} - {e}")
                        writer.write(
                            ProxyResponse(HTTPStatus.BAD_GATEWAY, headers={"Connection": "close"})
                        )
                        try:
                            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                        except Exception:
                            pass
                        return

                    writer.write(ProxyProtocol.CONNECTION_ESTABLISHED)
                    try:
                        await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                    except Exception:
                        pass
                    has_responded = True

                    try:
                        await self._tunnel(client, writer, dest_reader, dest_writer)
                    finally:
                        try:
                            dest_writer.close()
                            await dest_writer.wait_closed()
                        except Exception:
                            pass
                    return

                self.logger.info(f"Forwarding request to ({client_host}:{client_port})")

                content_length = get_content_length_from_request(request)

                host, port = extract_host_port_from_request(request)

                if not host or not host.strip():
                    self.logger.error("Invalid or empty host extracted from request")
                    writer.write(
                        ProxyResponse(HTTPStatus.BAD_REQUEST, headers={"Connection": "close"})
                    )
                    try:
                        await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                    except Exception:
                        pass
                    return

                try:
                    dest_reader, dest_writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), timeout=self.timeout
                    )
                except Exception as e:
                    self.logger.error(f"Error connecting to destination {host}:{port} - {e}")
                    writer.write(
                        ProxyResponse(HTTPStatus.BAD_GATEWAY, headers={"Connection": "close"})
                    )
                    try:
                        await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                    except Exception:
                        pass
                    return

                try:
                    forward_request = strip_proxy_authorization_header(request)
                    forward_request = ensure_connection_close_header(forward_request)

                    header_part, sep, body_initial = forward_request.partition(
                        ProxyProtocol.FINISHED
                    )
                    sent_all = False
                    if sep:
                        dest_writer.write(header_part + sep + body_initial)
                        try:
                            await asyncio.wait_for(dest_writer.drain(), timeout=self.timeout)
                        except Exception:
                            pass

                        initial_body_len = len(body_initial)
                        remaining = max(0, content_length - initial_body_len)

                        while remaining > 0:
                            chunk = await asyncio.wait_for(
                                client.read(min(4096, remaining)), timeout=self.timeout
                            )
                            if not chunk:
                                break
                            dest_writer.write(chunk)
                            try:
                                await asyncio.wait_for(dest_writer.drain(), timeout=self.timeout)
                            except Exception:
                                pass
                            remaining -= len(chunk)
                        sent_all = True

                    if not sent_all:
                        dest_writer.write(forward_request)
                        try:
                            await asyncio.wait_for(dest_writer.drain(), timeout=self.timeout)
                        except Exception:
                            pass

                    while True:
                        data = await asyncio.wait_for(dest_reader.read(4096), timeout=self.timeout)
                        if not data:
                            break
                        writer.write(data)
                        try:
                            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                        except Exception:
                            pass
                        if not has_responded:
                            has_responded = True
                except asyncio.TimeoutError:
                    self.logger.error("Timeout while forwarding to destination")
                    if not has_responded:
                        try:
                            writer.write(
                                ProxyResponse(
                                    HTTPStatus.GATEWAY_TIMEOUT, headers={"Connection": "close"}
                                )
                            )
                            await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                        except Exception:
                            pass
                except Exception as e:
                    self.logger.error(f"Error forwarding to destination: {e}")
                    if not has_responded:
                        try:
                            writer.write(
                                ProxyResponse(
                                    HTTPStatus.BAD_GATEWAY, headers={"Connection": "close"}
                                )
                            )
                            try:
                                await asyncio.wait_for(writer.drain(), timeout=self.timeout)
                            except Exception:
                                pass
                        except Exception:
                            pass
                finally:
                    try:
                        dest_writer.close()
                        await dest_writer.wait_closed()
                    except Exception:
                        pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

    async def _tunnel(
        self,
        client_reader: StreamReader,
        client_writer: StreamWriter,
        dest_reader: StreamReader,
        dest_writer: StreamWriter,
    ) -> None:
        async def _relay(src: StreamReader, dst: StreamWriter) -> None:
            while True:
                try:
                    data = await asyncio.wait_for(src.read(4096), timeout=self.timeout)
                    if not data:
                        break
                    dst.write(data)
                    try:
                        await asyncio.wait_for(dst.drain(), timeout=self.timeout)
                    except Exception:
                        pass
                except asyncio.TimeoutError:
                    break
                except Exception:
                    break

        task_up = asyncio.create_task(_relay(client_reader, dest_writer))
        task_down = asyncio.create_task(_relay(dest_reader, client_writer))

        done, pending = await asyncio.wait(
            {task_up, task_down}, return_when=asyncio.FIRST_COMPLETED
        )

        for t in pending:
            t.cancel()
            try:
                await t
            except Exception:
                pass
        try:
            dest_writer.close()
            await dest_writer.wait_closed()
        except Exception:
            pass
        try:
            client_writer.close()
            await client_writer.wait_closed()
        except Exception:
            pass
