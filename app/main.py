import logging

from core import Proxy, ProxyAuth, ProxyFirewall

logging.basicConfig(
    level=logging.DEBUG,  # Altere para DEBUG para ver logs de debug
    # format="%(asctime)s [%(levelname)s] %(message)s"
    format="[%(levelname)s] %(message)s",
)

auth = ProxyAuth(username="admin", password="admin")

firewall = ProxyFirewall(no_auth_required=["192.168.0.110"])

proxy = Proxy(auth=auth, firewall=firewall, production_mode=False)  # production_mode=False

proxy.run()
