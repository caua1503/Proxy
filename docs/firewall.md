## Firewall

O firewall atua sobre o IP de origem do cliente (quem se conecta ao proxy), e não sobre o host de destino.

### Opções

- `allowlist`: lista de IPs de cliente permitidos. Se vazia, não restringe por allowlist; se houver itens, somente esses IPs podem usar o proxy.
- `blocklist`: lista de IPs de cliente negados. Tem prioridade máxima: se um IP estiver aqui, será bloqueado mesmo que esteja na allowlist.
- `no_auth_required`: IPs de cliente dispensados de autenticação. Atenção: isso não ignora regras de allow/block.

### Regras de precedência

1. Se o IP do cliente estiver em `blocklist`, a conexão é bloqueada.
2. Se `allowlist` não estiver vazia, apenas IPs presentes nela são permitidos.
3. `no_auth_required` apenas dispensa autenticação; as regras de allow/block continuam valendo.

### Exemplo com allowlist

```python
from core import Proxy, ProxyFirewall

firewall = ProxyFirewall(
    allowlist=["10.0.0.5"]
)

proxy = Proxy(firewall=firewall)
proxy.run()
```

Teste (curl):

```bash
# somente o Host permitido ("10.0.0.5") funcionara o resto sera bloqueado
curl --proxy "http://ip_do_server:8080" "http://httpbin.org/ip"

```


### Exemplo com blocklist

```python
from core import Proxy, ProxyFirewall

firewall = ProxyFirewall(
    blocklist=["10.0.0.8"]

)

proxy = Proxy(firewall=firewall)
proxy.run()
```

Teste (curl):

```bash
# se o teste for executado a partir do IP de cliente 10.0.0.8, a conexão será negada
curl --proxy "http://ip_do_server:8080" "http://httpbin.org/ip"
```

### Exemplo com no_auth_required (dispensa autenticação para IPs específicos)

```python
from core import Proxy, ProxyFirewall

firewall = ProxyFirewall(
    no_auth_required=["10.0.0.1"]

)

auth = ProxyAuth(
    username="admin", 
    password="admin"
)

proxy = Proxy(auth=auth, firewall=firewall)
proxy.run()
```

Teste (curl):
cuidado ao configurar allowlist e blocklist para nao bloquear ip em no_auth_required

```bash
# somente o IP de cliente 10.0.0.1 poderá usar o proxy sem autenticação
curl --proxy "http://ip_do_server:8080" "http://httpbin.org/ip"
```



