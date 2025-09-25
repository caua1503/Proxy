## Motivação

### Meu uso

Este projeto é usado por uma aplicação de scraping que roda numa VPS. Como o IP é de datacenter, alguns sites acabam bloqueando. Para contornar isso, eu precisava de proxies residenciais, mas o preço desses proxies não cabe no meu orçamento. Então resolvi montar meu próprio servidor de proxy em Python.

A conectividade entre as máquinas (servidores de proxy) e a aplicação de scraping é feita por uma rede interna via VPN. Assim, cada máquina mantém seu IP público intacto e eu não redireciono tráfego pela rede da VPN; só crio uma rede interna entre elas para o tráfego do scraping.
