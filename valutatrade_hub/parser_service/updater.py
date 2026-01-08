# valutatrade_hub/parser_service/updater.py
"""
Основной модуль для обновления курсов валют.
"""
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from ..core.exceptions import ApiRequestError
from .config import ParserConfig
from .api_clients import BaseApiClient, ApiClientFactory
from .storage import RatesStorage


@dataclass
class UpdateResult:
    """Результат обновления курсов."""
    success: bool
    total_rates: int
    updated_pairs: List[str]
    failed_sources: List[str]
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


class RatesUpdater:
    """
    Класс для координации обновления курсов валют.
    """
    
    def __init__(
        self, 
        config: Optional[ParserConfig] = None,
        storage: Optional[RatesStorage] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.config = config or ParserConfig()
        self.storage = storage or RatesStorage(self.config)
        self.logger = logger or logging.getLogger(__name__)
        
        # Валидация конфигурации
        self._validate_config()
        
        # Создаем клиенты
        self.clients = self._initialize_clients()
    
    def _validate_config(self) -> None:
        """Валидация конфигурации."""
        errors = self.config.validate_config()
        if errors:
            for error in errors:
                self.logger.warning(f"Конфигурационная ошибка: {error}")
    
    def _initialize_clients(self) -> Dict[str, BaseApiClient]:
        """Инициализировать API клиенты."""
        clients = {}
        
        # CoinGecko клиент для криптовалют
        try:
            clients["coingecko"] = ApiClientFactory.create_client("coingecko", self.config)
            self.logger.info("CoinGecko клиент инициализирован")
        except Exception as e:
            self.logger.warning(f"Не удалось инициализировать CoinGecko клиент: {e}")
        
        # ExchangeRate-API клиент для фиатных валют
        try:
            clients["exchangerate"] = ApiClientFactory.create_client("exchangerate", self.config)
            self.logger.info("ExchangeRate-API клиент инициализирован")
        except Exception as e:
            self.logger.warning(f"Не удалось инициализировать ExchangeRate-API клиент: {e}")
        
        if not clients:
            raise RuntimeError("Не удалось инициализировать ни одного API клиента")
        
        return clients
    
    def run_update(
        self, 
        source_filter: Optional[str] = None,
        force_update: bool = False
    ) -> UpdateResult:
        """
        Запустить обновление курсов.
        
        Args:
            source_filter: Фильтр по источнику ("coingecko", "exchangerate")
            force_update: Принудительное обновление даже если курсы актуальны
            
        Returns:
            Результат обновления
        """
        start_time = time.time()
        result = UpdateResult(
            success=False,
            total_rates=0,
            updated_pairs=[],
            failed_sources=[]
        )
        
        try:
            self.logger.info(f"Начало обновления курсов (фильтр: {source_filter or 'все'})")
            
            # Определяем, какие клиенты использовать
            clients_to_use = self._select_clients(source_filter)
            
            if not clients_to_use:
                error_msg = f"Нет доступных клиентов для источника: {source_filter}"
                result.errors.append(error_msg)
                self.logger.error(error_msg)
                return result
            
            # Получаем курсы от всех клиентов
            all_rates = {}
            metadata = {
                "update_started": result.timestamp,
                "sources_used": list(clients_to_use.keys())
            }
            
            for source_name, client in clients_to_use.items():
                try:
                    self.logger.info(f"Получение курсов от {source_name}...")
                    
                    # Получаем курсы от клиента
                    rates = client.fetch_rates()
                    
                    # Объединяем с уже полученными курсами
                    all_rates.update(rates)
                    
                    self.logger.info(f"Получено {len(rates)} курсов от {source_name}")
                    
                except ApiRequestError as e:
                    error_msg = f"Ошибка при получении курсов от {source_name}: {e}"
                    result.errors.append(error_msg)
                    result.failed_sources.append(source_name)
                    self.logger.error(error_msg)
                except Exception as e:
                    error_msg = f"Неизвестная ошибка при работе с {source_name}: {e}"
                    result.errors.append(error_msg)
                    result.failed_sources.append(source_name)
                    self.logger.error(error_msg, exc_info=True)
            
            # Проверяем, есть ли новые курсы для обновления
            if not all_rates:
                error_msg = "Не удалось получить ни одного курса от всех источников"
                result.errors.append(error_msg)
                self.logger.error(error_msg)
                return result
            
            # Фильтруем курсы, которые действительно нужно обновить
            rates_to_update = {}
            
            for pair_key, rate in all_rates.items():
                if force_update or not self.storage.is_rate_fresh(pair_key):
                    rates_to_update[pair_key] = rate
                    result.updated_pairs.append(pair_key)
            
            if not rates_to_update and not force_update:
                self.logger.info("Все курсы актуальны, обновление не требуется")
                result.success = True
                result.total_rates = len(all_rates)
                return result
            
            # Определяем источник для сохранения
            if len(clients_to_use) == 1:
                source = list(clients_to_use.keys())[0]
            else:
                source = "multiple"
            
            # Сохраняем текущие курсы
            self.logger.info(f"Сохранение {len(rates_to_update)} курсов...")
            self.storage.save_current_rates(rates_to_update, source, metadata)
            
            # Сохраняем в историю
            self.logger.info("Сохранение в историю...")
            self.storage.save_to_history(rates_to_update, source, metadata)
            
            # Обновляем результат
            result.success = True
            result.total_rates = len(all_rates)
            result.duration_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                f"Обновление завершено. "
                f"Получено курсов: {len(all_rates)}, "
                f"Обновлено: {len(rates_to_update)}, "
                f"Затрачено времени: {result.duration_ms:.2f} мс"
            )
            
            # Делаем резервную копию
            try:
                backup_file = self.storage.backup()
                self.logger.info(f"Создана резервная копия: {backup_file}")
            except Exception as e:
                self.logger.warning(f"Не удалось создать резервную копию: {e}")
            
            return result
            
        except Exception as e:
            error_msg = f"Критическая ошибка при обновлении курсов: {e}"
            result.errors.append(error_msg)
            self.logger.error(error_msg, exc_info=True)
            return result
    
    def _select_clients(self, source_filter: Optional[str]) -> Dict[str, BaseApiClient]:
        """
        Выбрать клиенты для обновления.
        
        Args:
            source_filter: Фильтр по источнику
            
        Returns:
            Словарь клиентов
        """
        if not source_filter:
            return self.clients.copy()
        
        source_filter = source_filter.lower()
        
        if source_filter in self.clients:
            return {source_filter: self.clients[source_filter]}
        elif source_filter == "all":
            return self.clients.copy()
        else:
            self.logger.warning(f"Неизвестный источник: {source_filter}. Используются все клиенты.")
            return self.clients.copy()
    
    def get_update_status(self) -> Dict[str, Any]:
        """
        Получить статус последнего обновления.
        
        Returns:
            Информация о статусе
        """
        try:
            rates_data = self.storage.load_current_rates()
            metadata = rates_data.get("metadata", {})
            
            status = {
                "last_refresh": metadata.get("last_refresh"),
                "source": metadata.get("source"),
                "total_pairs": metadata.get("total_pairs", 0),
                "cache_status": {}
            }
            
            # Проверяем актуальность всех пар
            pairs = rates_data.get("pairs", {})
            fresh_count = 0
            stale_count = 0
            
            for pair_key in pairs.keys():
                if self.storage.is_rate_fresh(pair_key):
                    fresh_count += 1
                else:
                    stale_count += 1
            
            status["cache_status"] = {
                "fresh": fresh_count,
                "stale": stale_count,
                "total": len(pairs)
            }
            
            return status
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении статуса: {e}")
            return {
                "error": str(e),
                "last_refresh": None,
                "source": None,
                "total_pairs": 0,
                "cache_status": {"fresh": 0, "stale": 0, "total": 0}
            }
    
    def validate_rates(self, rates: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Валидация полученных курсов.
        
        Args:
            rates: Словарь курсов
            
        Returns:
            Кортеж (валидны ли курсы, список ошибок)
        """
        errors = []
        
        if not rates:
            errors.append("Пустой словарь курсов")
            return False, errors
        
        for pair_key, rate in rates.items():
            # Проверяем формат пары
            if "_" not in pair_key:
                errors.append(f"Некорректный формат пары: {pair_key}")
                continue
            
            from_curr, to_curr = pair_key.split("_", 1)
            
            # Проверяем коды валют
            if len(from_curr) < 2 or len(from_curr) > 5:
                errors.append(f"Некорректный код валюты: {from_curr}")
            
            if len(to_curr) < 2 or len(to_curr) > 5:
                errors.append(f"Некорректный код валюты: {to_curr}")
            
            # Проверяем значение курса
            if not isinstance(rate, (int, float)):
                errors.append(f"Некорректный тип курса для {pair_key}: {type(rate)}")
            elif rate <= 0:
                errors.append(f"Некорректное значение курса для {pair_key}: {rate}")
        
        return len(errors) == 0, errors