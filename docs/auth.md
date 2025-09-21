## Autenticação

### Esquema

- Suporte a autenticação básica via cabeçalho `Proxy-Authorization: Basic <base64(username:password)>`.
- Em caso de ausência/erro, responde `407 Proxy Authentication Required` com `Proxy-Authenticate: Basic realm="Proxy"`.

### Uso

Habilitar autenticação:

```python
from core import Proxy, ProxyAuth

auth = ProxyAuth(username="admin", password="admin")
proxy = Proxy(auth=auth)
proxy.run()
```

Requisição autenticada (curl):

```bash
curl --proxy "http://admin:admin@ip_do_server:8080" "http://httpbin.org/ip"
```

Sem autenticação (resposta 407):

```bash
curl --proxy "http://ip_do_server:8080" "http://httpbin.org/ip" -v
```

### Integração com firewall

- `no_auth_required`: IPs/hosts que não exigem autenticação, mesmo com `auth` habilitado.
- As regras de bloqueio/allowlist ainda se aplicam.

