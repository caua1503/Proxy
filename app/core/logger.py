"""
Logger do proxy.

Fornece uma camada de abstração sobre `logging` (biblioteca padrão do Python) para
padronizar formato, níveis e ponto único de configuração no projeto. Essa
abstração permite substituir a implementação por outra solução de logging sem
impactar os chamadores.

Recursos principais:
- Níveis suportados: INFO, WARNING, ERROR, DEBUG, CRITICAL.
- Formato padrão de saída: "[%(levelname)s]-[%(asctime)s] %(message)s".
- Classe `ProxyLogger` com métodos utilitários: `info`, `warning`, `error`, `debug`.
"""

import logging
from enum import IntEnum


class ProxyLogLevel(IntEnum):
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    DEBUG = logging.DEBUG
    CRITICAL = logging.CRITICAL


class ProxyLogger:
    def __init__(self, level: ProxyLogLevel = ProxyLogLevel.INFO):
        self.logger = logging.getLogger(__name__)
        self.level = level

        logging.basicConfig(level=self.level, format="[%(levelname)s] %(message)s")

    def info(self, message: str) -> None:
        self.logger.info(message)

    def warning(self, message: str) -> None:
        self.logger.warning(message)

    def error(self, message: str) -> None:
        self.logger.error(message)

    def critical(self, message: str) -> None:
        self.logger.critical(message)

    def debug(self, message: str) -> None:
        self.logger.debug(message)
