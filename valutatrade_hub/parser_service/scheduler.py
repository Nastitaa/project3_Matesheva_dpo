# valutatrade_hub/parser_service/scheduler.py
"""
Планировщик для периодического обновления курсов.
"""
import time
import threading
import schedule
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable

from .updater import RatesUpdater
from .config import ParserConfig


class ParserScheduler:
    """
    Планировщик для автоматического обновления курсов.
    """
    
    def __init__(
        self,
        config: Optional[ParserConfig] = None,
        updater: Optional[RatesUpdater] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.config = config or ParserConfig()
        self.updater = updater or RatesUpdater(config)
        self.logger = logger or logging.getLogger(__name__)
        
        self._scheduler_thread = None
        self._stop_event = threading.Event()
        self._is_running = False
        
        # Callback функции
        self._on_update_start: Optional[Callable] = None
        self._on_update_complete: Optional[Callable] = None
        self._on_error: Optional[Callable] = None
    
    def start(self, interval_minutes: Optional[int] = None) -> None:
        """
        Запустить планировщик.
        
        Args:
            interval_minutes: Интервал обновления в минутах
        """
        if self._is_running:
            self.logger.warning("Планировщик уже запущен")
            return
        
        interval = interval_minutes or self.config.UPDATE_INTERVAL_MINUTES
        
        self.logger.info(f"Запуск планировщика с интервалом {interval} минут")
        
        # Настраиваем расписание
        schedule.every(interval).minutes.do(self._scheduled_update)
        
        # Запускаем поток планировщика
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._run_scheduler,
            daemon=True,
            name="ParserScheduler"
        )
        self._scheduler_thread.start()
        
        self._is_running = True
        
        # Запускаем немедленное обновление при старте
        if self.config.update_on_start:
            self.logger.info("Запуск немедленного обновления...")
            self.run_update()
    
    def stop(self) -> None:
        """Остановить планировщик."""
        if not self._is_running:
            return
        
        self.logger.info("Остановка планировщика...")
        
        self._stop_event.set()
        schedule.clear()
        
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5.0)
        
        self._is_running = False
        self.logger.info("Планировщик остановлен")
    
    def run_update(self) -> bool:
        """
        Запустить немедленное обновление.
        
        Returns:
            True если обновление успешно
        """
        try:
            if self._on_update_start:
                self._on_update_start()
            
            self.logger.info("Запуск немедленного обновления курсов...")
            
            result = self.updater.run_update()
            
            if result.success:
                self.logger.info(
                    f"Немедленное обновление успешно. "
                    f"Обновлено курсов: {len(result.updated_pairs)}"
                )
                
                if self._on_update_complete:
                    self._on_update_complete(result)
                    
                return True
            else:
                self.logger.error(
                    f"Немедленное обновление завершено с ошибками: {result.errors}"
                )
                
                if self._on_error:
                    self._on_error(result.errors)
                    
                return False
                
        except Exception as e:
            error_msg = f"Ошибка при немедленном обновлении: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if self._on_error:
                self._on_error([error_msg])
            
            return False
    
    def get_next_run_time(self) -> Optional[datetime]:
        """
        Получить время следующего запуска.
        
        Returns:
            Время следующего запуска или None
        """
        try:
            jobs = schedule.get_jobs()
            if jobs:
                next_run = jobs[0].next_run
                if next_run:
                    return next_run
        except Exception as e:
            self.logger.warning(f"Не удалось получить время следующего запуска: {e}")
        
        return None
    
    def get_status(self) -> dict:
        """
        Получить статус планировщика.
        
        Returns:
            Словарь с информацией о статусе
        """
        status = {
            "is_running": self._is_running,
            "next_run": None,
            "update_interval_minutes": self.config.UPDATE_INTERVAL_MINUTES,
            "last_update": None
        }
        
        # Время следующего запуска
        next_run = self.get_next_run_time()
        if next_run:
            status["next_run"] = next_run.isoformat()
        
        # Информация о последнем обновлении
        update_status = self.updater.get_update_status()
        status["last_update"] = update_status.get("last_refresh")
        status.update(update_status)
        
        return status
    
    def set_callbacks(
        self,
        on_update_start: Optional[Callable] = None,
        on_update_complete: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ) -> None:
        """
        Установить callback функции.
        
        Args:
            on_update_start: Вызывается перед началом обновления
            on_update_complete: Вызывается после успешного обновления
            on_error: Вызывается при ошибке
        """
        self._on_update_start = on_update_start
        self._on_update_complete = on_update_complete
        self._on_error = on_error
    
    def _run_scheduler(self) -> None:
        """Основной цикл планировщика."""
        self.logger.info("Поток планировщика запущен")
        
        while not self._stop_event.is_set():
            try:
                schedule.run_pending()
                time.sleep(1)  # Проверяем каждую секунду
            except Exception as e:
                self.logger.error(f"Ошибка в планировщике: {e}", exc_info=True)
                time.sleep(5)  # Ждем перед повторной попыткой
        
        self.logger.info("Поток планировщика завершен")
    
    def _scheduled_update(self) -> None:
        """Запланированное обновление курсов."""
        try:
            if self._on_update_start:
                self._on_update_start()
            
            self.logger.info("Запуск запланированного обновления курсов...")
            
            result = self.updater.run_update()
            
            if result.success:
                self.logger.info(
                    f"Запланированное обновление успешно. "
                    f"Обновлено курсов: {len(result.updated_pairs)}"
                )
                
                if self._on_update_complete:
                    self._on_update_complete(result)
            else:
                self.logger.error(
                    f"Запланированное обновление завершено с ошибками: {result.errors}"
                )
                
                if self._on_error:
                    self._on_error(result.errors)
                    
        except Exception as e:
            error_msg = f"Ошибка при запланированном обновлении: {e}"
            self.logger.error(error_msg, exc_info=True)
            
            if self._on_error:
                self._on_error([error_msg])