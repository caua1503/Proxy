import logging

from core import Proxy, ProxyAuth

logging.basicConfig(
    level=logging.INFO,  # Altere para DEBUG para ver logs de debug
    # format="%(asctime)s [%(levelname)s] %(message)s"
    format="[%(levelname)s] %(message)s",
)
auth = ProxyAuth(username="admin", password="admin")

proxy = Proxy(auth=auth, production_mode=False)  # production_mode=False

proxy.run()
