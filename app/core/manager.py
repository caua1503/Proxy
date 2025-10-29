import asyncio
import time
from asyncio.streams import StreamReader, StreamWriter
from collections import defaultdict
from http import HTTPMethod, HTTPStatus
from typing import Literal, Optional
from urllib.parse import urlparse

from models import (
    ProxyConcurrentTable,
    ProxyManagerConfig,
    ProxyModel,
    ProxyTable,
)
from utils import (
    get_method_and_target_from_request,
    parse_headers_from_request,
)

from .auth import ProxyAuth
from .firewall import ProxyFirewall
from .logger import ProxyLogger, ProxyLogLevel
from .proxy import Proxy
from .response import ProxyProtocol, ProxyResponse


class ProxyManager:
    def __init__(
        self,
        proxy_url: list[ProxyModel],
        host: str = "0.0.0.0",
        port: int | str = 8889,
        debug: bool = False,
        auth: Optional[ProxyAuth] = None,
        firewall: Optional[ProxyFirewall] = None,
        webhook_mode: bool = False,
        timeout: int = 15,
        update_timeout: int = 30,
        logger: ProxyLogger = ProxyLogger(),
        proxy_server: Optional[Proxy] = None,
        extra_config: ProxyManagerConfig = ProxyManagerConfig(),
    ):
        self.proxy_url = proxy_url
        self.host = host
        self.port = int(port)
        self.debug = debug
        self.auth = auth
        self.firewall = firewall
        self.webhook_mode = webhook_mode
        self.timeout = timeout
        self.update_timeout = update_timeout
        self.proxy_server = proxy_server
        self.logger = logger if not debug else ProxyLogger(level=ProxyLogLevel.DEBUG)

        if self.proxy_server is not None:
            if not isinstance(self.proxy_server, Proxy):
                raise TypeError("Erro: 'proxy_server' deve ser uma instância de Proxy ou None.")

            original_logger = self.proxy_server.logger
            self.proxy_server.logger = ProxyLogger(level=original_logger.level, app_name="Proxy")

            proxy_host, proxy_port, proxy_auth = self.proxy_server.get_info()

            if proxy_host in set({"127.0.0.1", "localhost", "0.0.0.0"}) and proxy_port == self.port:
                self.logger.warning(
                    f"Proxy server na porta {proxy_port} não será adicionado como upstream para evitar loop infinito"  # noqa: E501
                )
            else:
                if proxy_auth is not None:
                    model = ProxyModel(
                        f"{proxy_auth.username}:{proxy_auth.password}@{proxy_host}:{proxy_port}"
                    )
                else:
                    model = ProxyModel(f"{proxy_host}:{proxy_port}")

                self.proxy_url.append(model)

        unique_proxies = []
        seen_urls = set()

        for proxy in proxy_url:
            if proxy.url not in seen_urls:
                seen_urls.add(proxy.url)
                unique_proxies.append(proxy)

        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._proxy_order_lock: asyncio.Lock = asyncio.Lock()
        self.proxy_url: list[ProxyModel] = unique_proxies
        self.proxy_concurrent_table = self._get_proxy_concurrent_table(self.proxy_url)

        """
        Extra Configs
        """

        self.target_url = extra_config.target_url
        self.retries = extra_config.target_url
        self.timeout_test = extra_config.timeout_test
        self.bath_size = extra_config.bath_size

        self.proxy_table: dict[str, ProxyTable] = {}
        # asyncio.run(self._get_proxy())

    async def _run(self) -> None:
        if self.proxy_server:
            asyncio.create_task(self.proxy_server.async_run())

        asyncio.create_task(self._update_proxy())
        await self._server()

    async def _server(self):
        self.logger.info("Starting ProxyManager")
        try:
            server = await asyncio.start_server(
                self._handle_client_request,
                self.host,
                self.port,
            )
        except Exception as e:
            self.logger.critical(f"Error starting async proxy server ({str(e)})")
            return

        self.logger.info(f"Proxy server started (http://{self.host}:{self.port})")

        if self.debug:
            self.logger.info("Debug mode enabled")

        async with server:
            try:
                await server.serve_forever()
            except asyncio.CancelledError:
                pass

    async def _handle_client_request(self, client: StreamReader, writer: StreamWriter) -> None:  # noqa: PLR0915, PLR0912, PLR0914
        PEER_TUPLE_MIN_LEN_FOR_PORT = 2
        peer = writer.get_extra_info("peername")
        client_host = peer[0] if isinstance(peer, tuple) and len(peer) >= 1 else "?"
        client_port = (
            peer[1] if isinstance(peer, tuple) and len(peer) >= PEER_TUPLE_MIN_LEN_FOR_PORT else -1
        )

        self.logger.debug(f"Request accepted de {client_host}:{client_port}")

        try:
            request = await asyncio.wait_for(client.readuntil(ProxyProtocol.FINISHED), timeout=self.timeout)
        except Exception:
            self.logger.warning(
                f"Timeout/erro lendo headers do cliente {client_host}:{client_port}"
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        if self.firewall and not self.firewall.verify(client_host):
            self.logger.info(
                f"Connection refused ({client_host}:{client_port}) - (firewall blocked)"
            )
            try:
                writer.write(ProxyResponse(HTTPStatus.FORBIDDEN, headers={"Connection": "close"}))
                await writer.drain()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            return

        if self.auth and not (self.firewall and self.firewall.is_no_auth_required(client_host)):
            headers = parse_headers_from_request(request)
            if not self.auth.is_authorized(headers):
                self.logger.info(
                    f"Connection refused ({client_host}:{client_port}) - (reauthentication required)"  # noqa: E501
                )
                writer.write(
                    ProxyResponse(
                        HTTPStatus.PROXY_AUTHENTICATION_REQUIRED, headers={"Connection": "close"}
                    )
                )
                await writer.drain()
                return

        method, target = get_method_and_target_from_request(request)

        try:
            proxy_url = await self._choose_proxy()
        except Exception as e:
            self.logger.error(f"Erro ao escolher proxy: {e}")
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        await self._update_proxy_concurrent(method="add", usage_proxy=proxy_url)

        try:
            parsed = urlparse(proxy_url)
            proxy_host = parsed.hostname
            proxy_port = parsed.port or 80
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(proxy_host, proxy_port), timeout=self.timeout
            )
        except Exception as e:
            self.logger.warning(f"Erro ao conectar ao proxy upstream {proxy_url}: {e}")
            await self._update_proxy_concurrent(method="remove", usage_proxy=proxy_url)
            writer.write(
                ProxyResponse(HTTPStatus.BAD_GATEWAY, headers=ProxyProtocol.CONNECTION_CLOSE)
            )
            await writer.drain()
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        async def pipe(reader, writer):
            try:
                while not reader.at_eof():
                    data = await reader.read(4096)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass

        try:
            if method == HTTPMethod.CONNECT:
                upstream_writer.write(ProxyProtocol.CONNECT_LINE(target))
                await upstream_writer.drain()
                response = await upstream_reader.readuntil(ProxyProtocol.FINISHED)
                writer.write(response)
                await writer.drain()
            else:
                upstream_writer.write(request)
                await upstream_writer.drain()

            pipe1 = asyncio.create_task(pipe(client, upstream_writer))
            pipe2 = asyncio.create_task(pipe(upstream_reader, writer))
            await asyncio.wait([pipe1, pipe2], return_when=asyncio.FIRST_COMPLETED)
        except Exception as e:
            self.logger.warning(f"Erro no repasse de dados: {e}")
        finally:
            await self._update_proxy_concurrent(method="remove", usage_proxy=proxy_url)
            try:
                upstream_writer.close()
                await upstream_writer.wait_closed()
            except Exception:
                pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _webhook(): ...

    @staticmethod
    def _get_proxy_concurrent_table(
        proxy_list: list[ProxyModel],
    ) -> dict[str, ProxyConcurrentTable]:
        """
        Final Version {
        "http://proxy1.com": {"concurrent": 0},
        "http://proxy2.com": {"concurrent": 0},
        }
        """
        return {proxy.url: {"concurrent": 0} for proxy in proxy_list}

    async def _health_check(self, proxy: ProxyModel) -> dict[str, float | None, bool]:
        """
        url, update time (velocidade), ativo ou nao
        """
        start_time = time.perf_counter()
        health = True
        try:
            parsed = urlparse(proxy.url)
            host = parsed.hostname
            port = parsed.port or 80

            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=self.timeout_test
            )

            latency = round(time.perf_counter() - start_time, 3)
            writer.close()

            await writer.wait_closed()

            minimum_latency = 10
            if latency >= minimum_latency:
                health = False
            return {"url": proxy.url, "latency": latency, "health": health}

        except Exception:
            return {"url": proxy.url, "latency": None, "health": False}

    def run(self) -> None:
        try:
            asyncio.run(self._run())
        except KeyboardInterrupt:
            self.logger.info("Servidor encerrado")

    async def async_run(self) -> None:
        return await self._run()

    async def _get_proxy(self) -> None:
        """
        Atualiza o proxy_table com informações de saúde dos proxies usando locks para concorrência
        """

        async def _process_update_task(results: tuple) -> int:
            health_proxies = 0
            update_tasks = []
            for result in results:
                if isinstance(result, Exception):
                    self.logger.warning(f"Erro no health check: {result}")
                    continue

                proxy_url = result["url"]
                lock = self.locks[proxy_url]
                update_tasks.append(
                    asyncio.create_task(self._update_proxy_table_entry(lock, proxy_url, result))
                )
                health_proxies += 1

            await asyncio.gather(*update_tasks)
            return health_proxies

        health_check_tasks = []
        health_proxies = 0

        for proxy in self.proxy_url:
            health_check_tasks.append(asyncio.create_task(self._health_check(proxy)))

            if len(health_check_tasks) >= self.bath_size:
                results = await asyncio.gather(*health_check_tasks, return_exceptions=True)
                health_proxies += await _process_update_task(results)

        if health_check_tasks:
            results = await asyncio.gather(*health_check_tasks, return_exceptions=True)
            health_proxies += await _process_update_task(results)

        if health_proxies == 0:
            self.logger.warning("Nenhum proxy saudável encontrado.")
        else:
            self.logger.debug(f"Encontrados {health_proxies} proxies saudáveis")

    async def _update_proxy_table_entry(
        self, lock: asyncio.Lock, proxy_url: str, health_result: dict
    ) -> None:
        """
        Atualiza uma entrada específica do proxy_table usando lock para thread safety
        """
        async with lock:
            self.proxy_table[proxy_url] = {"latency": health_result["latency"]}

    async def _update_proxy(self) -> None:
        while True:
            await self._get_proxy()
            await self._order_proxy()
            self.logger.debug("Lista de proxy atualizado")
            await asyncio.sleep(self.update_timeout)

    async def _order_proxy(self) -> None:
        """
        Ordena `self.proxy_url` com os critérios:
        1) Menor latência (desconhecida vai para o fim)
        2) Menor prioridade numérica (1 antes de 2, etc.)
        3) Maior `max_connections`
        Usa lock para evitar corrida durante a ordenação.
        """
        async with self._proxy_order_lock:

            def get_latency(url: str) -> Optional[float]:
                data = self.proxy_table.get(url)
                return None if data is None else data.get("latency")

            def sort_key(proxy: ProxyModel):
                latency = get_latency(proxy.url)

                latency_none_flag = latency is None
                latency_value = float("inf") if latency is None else float(latency)

                priority_value = proxy.priority

                max_conn_sort = -int(proxy.max_connections)

                return (latency_none_flag, latency_value, priority_value, max_conn_sort)

            try:
                self.proxy_url.sort(key=sort_key)
            except Exception as e:
                self.logger.debug(f"Falha ao ordenar proxies: {e}")

    async def _update_proxy_concurrent(self, method: Literal["add", "remove"], usage_proxy: str):
        lock = self.locks[usage_proxy]

        async with lock:
            if method == "add":
                self.proxy_concurrent_table[usage_proxy]["concurrent"] += 1
            elif method == "remove":
                self.proxy_concurrent_table[usage_proxy]["concurrent"] = max(
                    0, self.proxy_concurrent_table[usage_proxy]["concurrent"] - 1
                )
            else:
                ...

    async def _choose_proxy(self) -> str:
        if not self.proxy_url:
            raise Exception("Nenhum proxy disponível ou saudável!")

        best_proxy: Optional[ProxyModel] = None
        best_ratio: float = float("inf")

        for proxy in self.proxy_url:
            url = proxy.url
            current_concurrent = self.proxy_concurrent_table.get(url, {"concurrent": 0}).get(
                "concurrent", 0
            )
            max_conn = max(1, int(proxy.max_connections))
            load_ratio = current_concurrent / max_conn

            if load_ratio < best_ratio:
                best_ratio = load_ratio
                best_proxy = proxy

            if current_concurrent < proxy.max_connections and load_ratio == 0:
                return url

        if best_proxy is not None:
            return best_proxy.url

        return self.proxy_url[0].url
