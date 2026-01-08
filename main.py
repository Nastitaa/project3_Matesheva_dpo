# main.py
#!/usr/bin/env python3
"""
ValutaTrade Hub - Платформа для симуляции торговли валютами
"""

import sys
from valutatrade_hub.cli.interface import main as cli_main


def main():
    """Основная функция приложения"""
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
