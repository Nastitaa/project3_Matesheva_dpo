# valutatrade_hub/decorators.py
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from functools import wraps


def log_action(
    action_name: Optional[str] = None,
    level: int = logging.INFO,
    include_args: bool = True,
    include_result: bool = False,
    include_duration: bool = True,
    verbose: bool = False
):
    """
    Декоратор для логирования действий
    
    Args:
        action_name: Имя действия (если None, используется имя функции)
        level: Уровень логирования
        include_args: Включать ли аргументы в логи
        include_result: Включать ли результат в логи
        include_duration: Включать ли длительность выполнения
        verbose: Расширенное логирование (включает больше контекста)
    
    Returns:
        Декорированная функция
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            start_time = time.time()
            action = action_name or func.__name__.upper()
            
            # Подготовка контекста логирования
            log_extra = {'action': action}
            
            try:
                # Получение информации о пользователе (если есть)
                if args and hasattr(args[0], 'current_user'):
                    user = args[0].current_user
                    if user and hasattr(user, 'username'):
                        log_extra['username'] = user.username
                        log_extra['user_id'] = user.user_id
                elif len(args) >= 2 and isinstance(args[0], int):
                    # Предполагаем, что первый аргумент - user_id
                    log_extra['user_id'] = args[0]
                
                # Логирование аргументов
                if include_args:
                    # Безопасное логирование аргументов
                    safe_args = []
                    for i, arg in enumerate(args):
                        if i == 0 and hasattr(arg, '__class__'):
                            # Не логируем self объект полностью
                            safe_args.append(f"{arg.__class__.__name__} instance")
                        elif isinstance(arg, (int, float, str, bool, type(None))):
                            safe_args.append(str(arg))
                        else:
                            safe_args.append(type(arg).__name__)
                    
                    log_extra['args'] = safe_args
                    
                    # Безопасное логирование keyword arguments
                    safe_kwargs = {}
                    for key, value in kwargs.items():
                        if key.lower().endswith('password'):
                            safe_kwargs[key] = '***HIDDEN***'
                        elif isinstance(value, (int, float, str, bool, type(None))):
                            safe_kwargs[key] = value
                        else:
                            safe_kwargs[key] = type(value).__name__
                    
                    if safe_kwargs:
                        log_extra['kwargs'] = safe_kwargs
                
                # Выполнение функции
                result = func(*args, **kwargs)
                log_extra['result'] = 'OK'
                
                # Добавление результата в логи
                if include_result and result is not None:
                    if isinstance(result, (int, float, str, bool, type(None))):
                        log_extra['func_result'] = result
                    else:
                        log_extra['func_result_type'] = type(result).__name__
                
                # Добавление длительности выполнения
                if include_duration:
                    duration = time.time() - start_time
                    log_extra['duration_ms'] = round(duration * 1000, 2)
                
                # Дополнительное логирование для verbose режима
                if verbose:
                    log_extra['timestamp'] = datetime.now().isoformat()
                    log_extra['function'] = f"{func.__module__}.{func.__name__}"
                
                # Логирование успешного выполнения
                logger.log(level, f"Action '{action}' completed successfully", extra=log_extra)
                return result
                
            except Exception as e:
                # Логирование ошибки
                log_extra['result'] = 'ERROR'
                log_extra['error_type'] = type(e).__name__
                log_extra['error_message'] = str(e)
                
                if include_duration:
                    duration = time.time() - start_time
                    log_extra['duration_ms'] = round(duration * 1000, 2)
                
                # Логирование ошибки
                logger.error(f"Action '{action}' failed: {e}", extra=log_extra)
                
                # Проброс исключения дальше
                raise
        
        return wrapper
    return decorator


def confirm_action(message: str = "Подтвердить действие?"):
    """
    Декоратор для подтверждения действий
    
    Args:
        message: Сообщение для подтверждения
    
    Returns:
        Декорированная функция
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Проверяем, есть ли интерфейс с методом input
            if args and hasattr(args[0], 'input'):
                # В CLI интерфейсе
                answer = input(f"{message} (yes/no): ").strip().lower()
                if answer not in ['yes', 'y', 'да', 'д']:
                    print("Действие отменено")
                    return None
            else:
                # Вне CLI - логируем, но выполняем
                logger = logging.getLogger(func.__module__)
                logger.warning(f"Action '{func.__name__}' requires confirmation but no CLI context")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def cache_result(ttl_seconds: int = 300):
    """
    Декоратор для кэширования результатов функций
    
    Args:
        ttl_seconds: Время жизни кэша в секундах
    
    Returns:
        Декорированная функция
    """
    cache = {}
    cache_timestamps = {}
    
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Создаем ключ кэша
            cache_key = (
                func.__module__,
                func.__name__,
                args,
                frozenset(kwargs.items())
            )
            
            current_time = time.time()
            
            # Проверяем кэш
            if cache_key in cache:
                timestamp = cache_timestamps.get(cache_key, 0)
                if current_time - timestamp < ttl_seconds:
                    logger = logging.getLogger(func.__module__)
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cache[cache_key]
            
            # Вычисляем результат
            result = func(*args, **kwargs)
            
            # Сохраняем в кэш
            cache[cache_key] = result
            cache_timestamps[cache_key] = current_time
            
            return result
        return wrapper
    return decorator


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,)
):
    """
    Декоратор для повторных попыток при исключениях
    
    Args:
        max_retries: Максимальное количество попыток
        delay: Задержка между попытками в секундах
        exceptions: Кортеж исключений для перехвата
    
    Returns:
        Декорированная функция
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            logger = logging.getLogger(func.__module__)
            
            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.debug(f"Retry {attempt}/{max_retries} for {func.__name__}")
                    
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        time.sleep(delay * (attempt + 1))  # Экспоненциальная задержка
                    else:
                        logger.error(f"Failed after {max_retries} attempts: {e}")
                        raise
            
            # Этот код никогда не должен выполняться
            raise last_exception
        
        return wrapper
    return decorator


def measure_performance():
    """
    Декоратор для измерения производительности функций
    
    Returns:
        Декорированная функция
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            start_memory = 0  # Здесь можно добавить измерение памяти
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.perf_counter()
                duration = end_time - start_time
                
                logger = logging.getLogger(func.__module__)
                logger.debug(
                    f"Performance measurement for {func.__name__}: "
                    f"{duration:.6f} seconds",
                    extra={
                        'function': func.__name__,
                        'duration_seconds': duration,
                        'performance': 'MEASUREMENT'
                    }
                )
        
        return wrapper
    return decorator