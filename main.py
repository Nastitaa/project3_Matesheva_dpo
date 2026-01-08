#!/usr/bin/env python3
"""
ValutaTrade Hub - Платформа для симуляции торговли валютами
"""

import sys

from valutatrade_hub.cli.interface import main as cli_main
from valutatrade_hub.logging_config import setup_logging
from valutatrade_hub.infra.settings import settings


def main():
    """Основная функция приложения"""
    # Инициализируем логирование
    setup_logging(
        log_level=settings.log_level,
        log_dir=settings.log_dir
    )

    print("=" * 50)
    print("ValutaTrade Hub - Торговая платформа")
    print("=" * 50)

    try:
        cli_main()
    except KeyboardInterrupt:
        print("\n\nПриложение завершено пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()