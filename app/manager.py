from core import Proxy, ProxyLogger, ProxyLogLevel, ProxyManager, ProxyModel

proxy_url = []

app = ProxyManager(
    proxy_url=proxy_url, debug=True, proxy_server=Proxy(logger=ProxyLogger(ProxyLogLevel.INFO))
)

app.run()

