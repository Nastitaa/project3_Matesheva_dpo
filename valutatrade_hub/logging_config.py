# valutatrade_hub/logging_config.py
import logging
import logging.handlers
import json
import sys
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
from ..infra.settings import SettingsLoader


class JSONFormatter(logging.Formatter):
    """Форматтер для вывода логов в формате JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Добавляем дополнительные поля, если они есть
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'username'):
            log_data['username'] = record.username
        if hasattr(record, 'currency'):
            log_data['currency'] = record.currency
        if hasattr(record, 'amount'):
            log_data['amount'] = record.amount
        if hasattr(record, 'rate'):
            log_data['rate'] = record.rate
        if hasattr(record, 'result'):
            log_data['result'] = record.result
        if hasattr(record, 'error_type'):
            log_data['error_type'] = record.error_type
        if hasattr(record, 'error_message'):
            log_data['error_message'] = record.error_message
        
        # Добавляем exception info, если есть
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Форматтер для вывода логов в консоль"""
    
    COLOR_CODES = {
        'DEBUG': '\033[36m',  # Cyan
        'INFO': '\033[32m',   # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
        'CRITICAL': '\033[41m',  # Red background
    }
    RESET_CODE = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        levelname = record.levelname
        color = self.COLOR_CODES.get(levelname, '')
        
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Формируем основное сообщение
        message = f"{timestamp} {levelname:8} {record.module}:{record.funcName}:{record.lineno} - {record.getMessage()}"
        
        # Добавляем дополнительные поля
        extra_parts = []
        if hasattr(record, 'action'):
            extra_parts.append(f"action={record.action}")
        if hasattr(record, 'user_id'):
            extra_parts.append(f"user_id={record.user_id}")
        if hasattr(record, 'currency'):
            extra_parts.append(f"currency={record.currency}")
        if hasattr(record, 'amount'):
            extra_parts.append(f"amount={record.amount}")
        if hasattr(record, 'result'):
            extra_parts.append(f"result={record.result}")
        
        if extra_parts:
            message += f" [{', '.join(extra_parts)}]"
        
        # Добавляем цвет для консоли
        if color and sys.stderr.isatty():
            message = f"{color}{message}{self.RESET_CODE}"
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            message += f"\n{self.formatException(record.exc_info)}"
        
        return message


def setup_logging() -> None:
    """Настройка логирования приложения"""
    settings = SettingsLoader()
    logging_config = settings.get_logging_config()
    
    # Получаем параметры конфигурации
    log_level = getattr(logging, logging_config.get('level', 'INFO'))
    log_format = logging_config.get('format', 'text')
    log_file = logging_config.get('file', 'logs/valutatrade.log')
    max_size_mb = logging_config.get('max_size_mb', 10)
    backup_count = logging_config.get('backup_count', 5)
    enable_console = logging_config.get('enable_console', True)
    enable_file = logging_config.get('enable_file', True)
    
    # Создаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Удаляем существующие обработчики
    root_logger.handlers.clear()
    
    # Настройка форматера
    if log_format == 'json':
        formatter = JSONFormatter()
    else:
        formatter = ConsoleFormatter()
    
    # Консольный обработчик
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    # Файловый обработчик с ротацией
    if enable_file:
        # Создаем директорию для логов, если ее нет
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Ротация по размеру файла
        max_bytes = max_size_mb * 1024 * 1024
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        
        if log_format == 'json':
            file_handler.setFormatter(JSONFormatter())
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
        
        root_logger.addHandler(file_handler)
    
    # Настройка логгеров для конкретных модулей
    module_loggers = {
        'valutatrade_hub': logging.INFO,
        'valutatrade_hub.core': logging.INFO,
        'valutatrade_hub.cli': logging.INFO,
        'valutatrade_hub.infra': logging.INFO,
    }
    
    for module, level in module_loggers.items():
        module_logger = logging.getLogger(module)
        module_logger.setLevel(level)
        module_logger.propagate = True  # Пропускаем логи в корневой логгер
    
    # Логируем начало работы
    root_logger.info("Логирование настроено", extra={
        'level': logging.getLevelName(log_level),
        'format': log_format,
        'file': log_file
    })


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер по имени
    
    Args:
        name: Имя логгера
    
    Returns:
        Объект логгера
    """
    return logging.getLogger(name)


def log_action(level: int = logging.INFO):
    """
    Декоратор для логирования действий
    
    Args:
        level: Уровень логирования
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            
            # Подготовка дополнительных полей
            extra = {
                'action': func.__name__.upper(),
                'result': 'OK'
            }
            
            try:
                # Выполнение функции
                result = func(*args, **kwargs)
                
                # Логирование успешного выполнения
                logger.log(level, f"Action '{func.__name__}' completed", extra=extra)
                return result
                
            except Exception as e:
                # Логирование ошибки
                extra['result'] = 'ERROR'
                extra['error_type'] = type(e).__name__
                extra['error_message'] = str(e)
                
                logger.error(f"Action '{func.__name__}' failed: {e}", extra=extra)
                raise
        
        return wrapper
    return decorator