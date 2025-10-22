import asyncio

from models import ProxyModel

from .auth import ProxyAuth
from .firewall import ProxyFirewall
from .logger import ProxyLogger, ProxyLogLevel
from .manager import ProxyManager
from .proxy import Proxy, SyncProxy

logger = ProxyLogger()
try:
    import uvloop  # type: ignore

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.info("Using uvloop")
except ImportError:
    pass

__all__ = [
    "Proxy",
    "SyncProxy",
    "ProxyAuth",
    "ProxyFirewall",
    "ProxyManager",
    "ProxyModel",
    "ProxyLogLevel",
]
