#!/usr/bin/env python3
"""
Запуск сервиса парсинга курсов валют.
Может использоваться как отдельный сервис.
"""
import sys
import argparse
import logging
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.updater import RatesUpdater
from valutatrade_hub.parser_service.scheduler import ParserScheduler
from valutatrade_hub.logging_config import setup_logging, get_logger


def run_once(config: ParserConfig) -> bool:
    """Запустить однократное обновление."""
    logger = get_logger(__name__)
    
    try:
        logger.info("Запуск однократного обновления курсов")
        
        updater = RatesUpdater(config)
        result = updater.run_update()
        
        if result.success:
            logger.info(
                f"Обновление успешно. "
                f"Обновлено курсов: {len(result.updated_pairs)}"
            )
            return True
        else:
            logger.error(
                f"Обновление завершено с ошибками: {result.errors}"
            )
            return False
            
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return False


def run_scheduler(config: ParserConfig, interval_minutes: int) -> None:
    """Запустить фоновый планировщик."""
    logger = get_logger(__name__)
    
    try:
        logger.info(f"Запуск планировщика с интервалом {interval_minutes} минут")
        
        scheduler = ParserScheduler(config)
        
        # Устанавливаем логирование в callback
        def on_update_start():
            logger.info("Начато автоматическое обновление курсов")
        
        def on_update_complete(result):
            logger.info(
                f"Автоматическое обновление завершено. "
                f"Обновлено курсов: {len(result.updated_pairs)}"
            )
        
        def on_error(errors):
            for error in errors:
                logger.error(f"Ошибка при обновлении: {error}")
        
        scheduler.set_callbacks(on_update_start, on_update_complete, on_error)
        
        # Запускаем планировщик
        scheduler.start(interval_minutes)
        
        logger.info("Планировщик запущен. Для остановки нажмите Ctrl+C")
        
        # Бесконечный цикл для удержания программы
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Получен сигнал остановки")
        finally:
            scheduler.stop()
            
    except Exception as e:
        logger.error(f"Критическая ошибка в планировщике: {e}", exc_info=True)
        raise


def main():
    """Основная функция запуска парсера."""
    parser = argparse.ArgumentParser(
        description="Сервис парсинга курсов валют ValutaTrade Hub"
    )
    parser.add_argument(
        '--mode',
        choices=['once', 'daemon'],
        default='once',
        help='Режим работы: once - однократно, daemon - фоновый режим'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=5,
        help='Интервал обновления в минутах (только для daemon режима)'
    )
    parser.add_argument(
        '--source',
        choices=['coingecko', 'exchangerate', 'all'],
        default='all',
        help='Источник данных'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Путь к файлу конфигурации'
    )
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Уровень логирования'
    )
    
    args = parser.parse_args()
    
    # Настройка логирования
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = get_logger(__name__)
    
    try:
        # Загружаем конфигурацию
        config = ParserConfig()
        
        # Валидация конфигурации
        errors = config.validate_config()
        if errors:
            for error in errors:
                logger.error(f"Ошибка конфигурации: {error}")
            
            if config.EXCHANGERATE_API_KEY == "demo_key":
                logger.warning(
                    "Для реального использования установите переменную окружения "
                    "EXCHANGERATE_API_KEY с вашим API ключом"
                )
        
        print(f"\n{'='*60}")
        print(f"ValutaTrade Hub - Сервис парсинга курсов валют")
        print(f"{'='*60}")
        print(f"Режим: {args.mode}")
        print(f"Интервал: {args.interval} минут" if args.mode == 'daemon' else "")
        print(f"Источник: {args.source}")
        print(f"Базовая валюта: {config.BASE_FIAT_CURRENCY}")
        print(f"TTL кэша: {config.CACHE_TTL_SECONDS} секунд")
        print(f"Фиатные валюты: {len(config.FIAT_CURRENCIES)}")
        print(f"Криптовалюты: {len(config.CRYPTO_CURRENCIES)}")
        print(f"{'='*60}\n")
        
        if args.mode == 'once':
            # Однократное выполнение
            success = run_once(config)
            sys.exit(0 if success else 1)
        else:
            # Фоновый режим
            run_scheduler(config, args.interval)
            
    except KeyboardInterrupt:
        logger.info("Сервис остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()