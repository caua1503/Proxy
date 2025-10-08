from core import Proxy

# auth = ProxyAuth(username="admin", password="admin")

# firewall = ProxyFirewall()

proxy = Proxy(debug=True)

proxy.run()
