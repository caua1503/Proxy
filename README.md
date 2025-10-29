## Servidor Proxy em Python

Este projeto é um servidor de proxy simples, desenvolvido em Python puro, com foco em gerenciar proxies internos e atender a demandas de pequena escala.

### Sumário

- [Características](#características)
- [Objetivo](#objetivo)
- [Motivação e contexto](#motivação-e-contexto)
- [Tecnologias](#tecnologias)
- [Instalação](#instalação)
- [Uso rápido](#uso-rápido)
- [Configuração](#configuração)
- [Autenticação](#autenticação)
- [Logs](#logs)
- [Possíveis usos](#possíveis-usos)
- [Roadmap](#roadmap)
- [Referências](#referências)

### Características

- Implementação leve e sem dependências externas (python puro).
- Ideal para uso em ambientes de produção controlado, ambientes de teste ou redes locais.
- Fácil de configurar e estender.

### Objetivo

Fornecer uma solução prática e minimalista para quem precisa de um proxy funcional, sem a complexidade de grandes ferramentas já existentes.

### Motivação e contexto

A ideia é basicamente criar um proxy e um servidor HTTP simples usando apenas Python, para estudos, testes e necessidades internas de baixa complexidade.

Este projeto é utilizado por uma aplicação interna: uma rede de proxies conectados via VPN. Veja mais em [Motivação](docs/motivacao.md).

- Grande parte do core foi inspirado pelo artigo do blog da Bright Data, o guia “Python Proxy Server” ([link](https://brightdata.com.br/blog/proxies-101/python-proxy-server)). 
- A partir dessa base, adotei minhas próprias metodologias de projeto, como a organização em classes, validações de entrada e fluxo.
- Implementei sistema de autenticação simples, sistema de firewall e suporte a tunelamento (metodo CONNECT).

### Tecnologias

- Python (>= 3.11)
- Uvloop (Opcional)
- Sem frameworks adicionais

### Instalação

1. Clone o repositório
2. Certifique-se de ter o Python 3.11 instalado
3. (Opcional) Crie e ative um ambiente virtual
4. Não há dependências externas a instalar

### Uso rápido

Execute o servidor:

```bash
python main.py
```

Por padrão o proxy sobe em `0.0.0.0:8080`.

Exemplo de teste via curl usando o proxy:

```bash
curl --proxy "http://admin:admin@ip_do_server:8080" "http://httpbin.org/ip"
```

### Configuração

A configuração principal é feita ao instanciar `core.Proxy` (veja `main.py`):

- `host` (str): endereço de bind. Padrão: `0.0.0.0`
- `port` (int): porta de escuta. Padrão: `8080`
- `backlog` (int): tamanho da fila de conexões pendentes no `listen()`. Padrão: `20`
- `max_connections` (int): máximo de requisições processadas em paralelo (pool de threads). Padrão: `20`
- `auth` (`ProxyAuth | None`): autenticação básica. Quando `None`, desabilita auth.
- `firewall` (`ProxyFirewall | None`): regras de allowlist/blocklist e `no_auth_required`.
- `debug` (bool): quando `True`, usa timeouts curtos para facilitar debug. Padrão: `False`
- `timeout` (int): tempo de timeout para as conexões

Para alterar rapidamente, edite `main.py`:

```python
from core import Proxy

proxy = Proxy()
proxy.run()
```

Exemplo de teste via curl usando o proxy, apenas instanciando a classe:

```bash
curl --proxy "http://ip_do_server:8080" "http://httpbin.org/ip"
```

#### Concorrência e desempenho

- `backlog` controla apenas a fila de conexões ainda não aceitas (antes do `accept()`).
- `max_connections` controla quantas requisições são atendidas simultaneamente.
- Recomenda-se configurar `backlog >= max_connections` para cenários com bursts/picos, mas não é obrigatório. Em máquinas com pouca carga, valores menores podem ser suficientes.

Exemplos:

```python
Proxy(backlog=50, max_connections=50)
Proxy(backlog=15, max_connections=10)
```

### Autenticação

Autenticação básica (HTTP Proxy-Authorization: Basic) é suportada. Quando habilitada (`auth` não nulo), o proxy exige credenciais e responde `407 Proxy Authentication Required` quando ausentes/incorretas.

- Cabeçalho usado: `Proxy-Authorization: Basic <base64(username:password)>`
- Para desabilitar a autenticação, passe `auth=None` ao `Proxy`.

Exemplo com `curl` (inclui usuário e senha na URL do proxy):

```bash
curl --proxy "http://usuario:senha@ip_do_server:8080" "http://httpbin.org/ip"
```

### Logs

Os logs usam o módulo `logging` do Python. Níveis:

- `INFO` (padrão em `main.py`)
- Ajuste para `DEBUG` em `logging.basicConfig(level=logging.DEBUG)` para ver tráfego e detalhes de forwarding.

### Possíveis usos

- Gerenciamento de tráfego interno.
- Proxy em ambientes de desenvolvimento.
- Estudos e aprendizado sobre redes e sockets em Python.

### Roadmap

- [x] Suporte a HTTPS CONNECT
- [x] Regras de bloqueio/allowlist
- [ ] Métricas e healthcheck

### Referências

- Bright Data — Python Proxy Server: [link](https://brightdata.com.br/blog/proxies-101/python-proxy-server)

### Mais informações

- [Detalhes do Proxy](docs/proxy.md)
- [Autenticação](docs/auth.md)
- [Firewall](docs/firewall.md)