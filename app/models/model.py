from dataclasses import dataclass
from typing import Optional, TypedDict


class ProxyConcurrentTable(TypedDict):
    """
    Final Version
    {
        "http://proxy1.com": {"concurrent": 0},
        "http://proxy2.com": {"concurrent": 0},
    }

    """

    concurrent: int


class ProxyTable(TypedDict):
    """
    Final Version
    {
        "http://proxy1.com": {"latency": 0.580},
        "http://proxy2.com": {"latency": None},
    }

    """

    latency: Optional[int] = None


@dataclass
class ProxyModel:
    """Configuração de um proxy.

    Args:
        url (str): Endereço do proxy.
        max_connections (int, optional): Máximo de conexões simultâneas. Padrão é 1000.
        priority (int, optional): Prioridade do proxy (1=alta, 2=media, 3=baixa). Padrão é 2.
    """

    url: str
    max_connections: int = 1000
    priority: int = 2

    def __post_init__(self):
        if not self.url.startswith(("http", "https")):
            self.url = f"http://{self.url.lstrip('/')}"


@dataclass
class ProxyManagerConfig:
    target_url: str = "https://httpbin.org/ip"  # ("https://api.exemplo.com")
    timeout_test: int = 2
    retries: int = 3
    bath_size: int = 1000
    test_mode: TestedModeType = "accurate"
