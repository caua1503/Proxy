"""
Logger do proxy.

Fornece uma camada de abstração sobre `logging` (biblioteca padrão do Python) para
padronizar formato, níveis e ponto único de configuração no projeto. Essa
abstração permite substituir a implementação por outra solução de logging sem
impactar os chamadores.

Recursos principais:
- Níveis internos independentes: DEBUG(0), INFO(1), WARNING(2), ERROR(3), CRITICAL(4).
- Filtragem interna baseada em valores numéricos sequenciais.
- Formato padrão de saída: "[%(levelname)s] %(message)s".
- Classe `ProxyLogger` com métodos utilitários: `info`, `warning`, `error`, `debug`, `critical`.
- Método genérico `log(level, message)` para uso direto.
- Método `set_level(level)` para alterar nível em runtime.
"""

import logging
from enum import IntEnum


class ProxyLogLevel(IntEnum):
    """
    Níveis de log internos, independentes do logging padrão do Python.
    Valores sequenciais começando do 0, onde números maiores indicam maior severidade.
    """

    DEBUG = 0  # Mais verboso, para desenvolvimento
    INFO = 1  # Informações gerais
    WARNING = 2  # Avisos que não impedem execução
    ERROR = 3  # Erros que impedem funcionalidade específica
    CRITICAL = 4  # Erros críticos que podem parar o sistema


class ProxyLogger:
    # Tabela interna de mapeamento para níveis do logging
    _LEVEL_MAPPING = {
        ProxyLogLevel.DEBUG: logging.DEBUG,
        ProxyLogLevel.INFO: logging.INFO,
        ProxyLogLevel.WARNING: logging.WARNING,
        ProxyLogLevel.ERROR: logging.ERROR,
        ProxyLogLevel.CRITICAL: logging.CRITICAL,
    }

    def __init__(self, level: ProxyLogLevel = ProxyLogLevel.INFO):
        self.logger = logging.getLogger(__name__)
        self.level = level

        logging.basicConfig(level=logging.NOTSET, format="[%(levelname)s] %(message)s")

    def set_level(self, level: ProxyLogLevel) -> None:
        self.level = level

    def _should_emit(self, message_level: ProxyLogLevel) -> bool:
        return int(message_level) >= int(self.level)

    def log(self, level: ProxyLogLevel, message: str) -> None:
        if self._should_emit(level):
            logging_level = self._LEVEL_MAPPING[level]
            self.logger.log(logging_level, message)

    def info(self, message: str) -> None:
        self.log(ProxyLogLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.log(ProxyLogLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.log(ProxyLogLevel.ERROR, message)

    def critical(self, message: str) -> None:
        self.log(ProxyLogLevel.CRITICAL, message)

    def debug(self, message: str) -> None:
        self.log(ProxyLogLevel.DEBUG, message)
