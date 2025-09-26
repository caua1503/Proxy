## Suporte Assíncrono

### Implementação

Para o suporte assíncrono foi utilizada a biblioteca `asyncio` padrão do Python.

A biblioteca `asyncio` não tem backlogs por padrão e também não tem limites explicitamente definidos de concorrência, então foi implementado o `Semaphore` para controle de concorrência.

A função `asyncio.start_server()` aceita a função que vai fazer a comunicação, mais os parâmetros host e port, abstraindo a biblioteca sockets.

### Comparação: Síncrono vs Assíncrono

| Problema no síncrono                                            | Como o assíncrono resolve                     |
| --------------------------------------------------------------- | --------------------------------------------- |
| Consumo de RAM com muitas threads                               | Usa corrotinas leves em um único loop         |
| Context switching pesado                                        | Troca cooperativa via `await`, mais eficiente |
| Dificuldade em lidar com **muitos clientes de uma vez** (1000+) | `asyncio` escala facilmente para milhares     |
| Bloqueios por operações longas                                  | `await` libera o loop para outros clientes    |
| Controle de timeouts limitado (socket.settimeout)               | `asyncio.wait_for` em cada operação           |

### Conclusão

O síncrono com threads é simples e funciona bem em pequena escala.
O assíncrono resolve os gargalos de escalabilidade e custo de recursos, sendo a escolha ideal para proxies modernos que precisam lidar com milhares de conexões.