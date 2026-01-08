# valutatrade_hub/parser_service/api_clients.py
"""
Клиенты для работы с внешними API курсов валют.
"""
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from ..core.exceptions import ApiRequestError
from .config import ParserConfig


class BaseApiClient(ABC):
    """Абстрактный базовый класс для API клиентов."""
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ValutaTradeHub/1.0",
            "Accept": "application/json",
        })
    
    @abstractmethod
    def fetch_rates(self) -> Dict[str, float]:
        """Получить курсы валют."""
        pass
    
    def _make_request(
        self, 
        url: str, 
        params: Optional[Dict] = None,
        max_retries: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Выполнить HTTP запрос с обработкой ошибок и повторными попытками.
        
        Args:
            url: URL для запроса
            params: Параметры запроса
            max_retries: Максимальное количество попыток
            
        Returns:
            Ответ API в виде словаря
            
        Raises:
            ApiRequestError: При ошибке запроса
        """
        if max_retries is None:
            max_retries = self.config.MAX_RETRIES
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.config.REQUEST_TIMEOUT
                )
                
                # Проверка статуса ответа
                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:  # Too Many Requests
                    retry_after = int(response.headers.get('Retry-After', 60))
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                        continue
                    else:
                        raise ApiRequestError(
                            f"Превышен лимит запросов. Попробуйте через {retry_after} секунд.",
                            status_code=429
                        )
                elif response.status_code == 401:
                    raise ApiRequestError("Неверный API ключ", status_code=401)
                elif response.status_code == 403:
                    raise ApiRequestError("Доступ запрещен", status_code=403)
                elif response.status_code == 404:
                    raise ApiRequestError("Ресурс не найден", status_code=404)
                else:
                    raise ApiRequestError(
                        f"Ошибка API: {response.status_code} - {response.text}",
                        status_code=response.status_code
                    )
                    
            except (Timeout, ConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = self.config.RETRY_DELAY * (attempt + 1)
                    time.sleep(delay)
                else:
                    raise ApiRequestError(
                        f"Ошибка сети после {max_retries} попыток: {str(e)}"
                    )
            except json.JSONDecodeError as e:
                raise ApiRequestError(f"Ошибка декодирования JSON: {str(e)}")
            except RequestException as e:
                raise ApiRequestError(f"Ошибка запроса: {str(e)}")
        
        # Этот код никогда не должен выполняться
        if last_exception:
            raise ApiRequestError(f"Неизвестная ошибка: {str(last_exception)}")
        else:
            raise ApiRequestError("Неизвестная ошибка при выполнении запроса")
    
    def _get_timestamp(self) -> str:
        """Получить текущую метку времени в ISO формате."""
        return datetime.utcnow().isoformat() + "Z"


class CoinGeckoClient(BaseApiClient):
    """Клиент для работы с CoinGecko API (криптовалюты)."""
    
    def fetch_rates(self) -> Dict[str, float]:
        """
        Получить курсы криптовалют от CoinGecko.
        
        Returns:
            Словарь вида {"BTC_USD": 59337.21, ...}
        """
        try:
            # Формируем URL для запроса
            url = self.config.coingecko_simple_price_url
            
            # Добавляем небольшую задержку для избежания лимитов
            time.sleep(self.config.COINGECKO_REQUEST_DELAY)
            
            # Выполняем запрос
            data = self._make_request(url)
            
            # Преобразуем данные в стандартный формат
            rates = {}
            timestamp = self._get_timestamp()
            
            for crypto_code, gecko_id in self.config.CRYPTO_ID_MAP.items():
                if gecko_id in data and "usd" in data[gecko_id]:
                    pair_key = f"{crypto_code}_{self.config.BASE_CRYPTO_CURRENCY}"
                    rate = float(data[gecko_id]["usd"])
                    rates[pair_key] = rate
            
            if not rates:
                raise ApiRequestError("Не удалось получить курсы криптовалют от CoinGecko")
            
            return rates
            
        except Exception as e:
            raise ApiRequestError(f"Ошибка при получении курсов от CoinGecko: {str(e)}")
    
    def get_rate_history(
        self, 
        crypto_id: str, 
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Получить исторические данные по криптовалюте.
        
        Args:
            crypto_id: ID криптовалюты в CoinGecko
            days: Количество дней истории
            
        Returns:
            Исторические данные
        """
        try:
            url = f"{self.config.COINGECKO_BASE_URL}/coins/{crypto_id}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": days
            }
            
            time.sleep(self.config.COINGECKO_REQUEST_DELAY)
            return self._make_request(url, params=params)
            
        except Exception as e:
            raise ApiRequestError(f"Ошибка при получении истории от CoinGecko: {str(e)}")


class ExchangeRateApiClient(BaseApiClient):
    """Клиент для работы с ExchangeRate-API (фиатные валюты)."""
    
    def fetch_rates(self) -> Dict[str, float]:
        """
        Получить курсы фиатных валют от ExchangeRate-API.
        
        Returns:
            Словарь вида {"EUR_USD": 1.0786, ...}
        """
        try:
            # Формируем URL для запроса
            url = self.config.exchangerate_api_url
            
            # Выполняем запрос
            data = self._make_request(url)
            
            # Проверяем успешность запроса
            if data.get("result") != "success":
                error_type = data.get("error-type", "unknown")
                raise ApiRequestError(f"Ошибка ExchangeRate-API: {error_type}")
            
            # Извлекаем курсы
            base_currency = data.get("base_code", "USD")
            rates_data = data.get("rates", {})
            
            # Преобразуем данные в стандартный формат
            rates = {}
            timestamp = self._get_timestamp()
            
            for currency_code, rate in rates_data.items():
                # Пропускаем базовую валюту
                if currency_code == base_currency:
                    continue
                
                # Проверяем, что валюта в нашем списке отслеживания
                if currency_code in self.config.FIAT_CURRENCIES:
                    pair_key = f"{currency_code}_{base_currency}"
                    rates[pair_key] = float(rate)
            
            if not rates:
                raise ApiRequestError("Не удалось получить курсы фиатных валют от ExchangeRate-API")
            
            return rates
            
        except Exception as e:
            raise ApiRequestError(f"Ошибка при получении курсов от ExchangeRate-API: {str(e)}")
    
    def convert_currency(
        self, 
        amount: float, 
        from_currency: str, 
        to_currency: str
    ) -> Dict[str, Any]:
        """
        Конвертировать сумму из одной валюты в другую.
        
        Args:
            amount: Сумма для конвертации
            from_currency: Исходная валюта
            to_currency: Целевая валюта
            
        Returns:
            Результат конвертации
        """
        try:
            url = f"{self.config.EXCHANGERATE_API_BASE_URL}/{self.config.EXCHANGERATE_API_KEY}/pair/{from_currency}/{to_currency}/{amount}"
            
            data = self._make_request(url)
            
            if data.get("result") != "success":
                error_type = data.get("error-type", "unknown")
                raise ApiRequestError(f"Ошибка конвертации: {error_type}")
            
            return data
            
        except Exception as e:
            raise ApiRequestError(f"Ошибка при конвертации валюты: {str(e)}")


class MockApiClient(BaseApiClient):
    """
    Mock клиент для тестирования.
    Возвращает заранее заданные курсы.
    """
    
    def __init__(self, config: ParserConfig, rates: Optional[Dict[str, float]] = None):
        super().__init__(config)
        self._rates = rates or {
            "BTC_USD": 59337.21,
            "ETH_USD": 3720.00,
            "EUR_USD": 1.0786,
            "GBP_USD": 1.2634,
        }
    
    def fetch_rates(self) -> Dict[str, float]:
        """Возвращает mock курсы."""
        # Имитируем задержку сети
        time.sleep(0.1)
        return self._rates.copy()


class ApiClientFactory:
    """Фабрика для создания API клиентов."""
    
    @staticmethod
    def create_client(
        client_type: str,
        config: ParserConfig
    ) -> BaseApiClient:
        """
        Создать клиент указанного типа.
        
        Args:
            client_type: Тип клиента ("coingecko", "exchangerate", "mock")
            config: Конфигурация
            
        Returns:
            Экземпляр клиента
            
        Raises:
            ValueError: При неизвестном типе клиента
        """
        client_type = client_type.lower()
        
        if client_type == "coingecko":
            return CoinGeckoClient(config)
        elif client_type == "exchangerate":
            return ExchangeRateApiClient(config)
        elif client_type == "mock":
            return MockApiClient(config)
        else:
            raise ValueError(f"Неизвестный тип клиента: {client_type}")
    
    @staticmethod
    def create_all_clients(config: ParserConfig) -> Dict[str, BaseApiClient]:
        """Создать все доступные клиенты."""
        clients = {}
        
        try:
            clients["coingecko"] = CoinGeckoClient(config)
        except Exception as e:
            print(f"⚠️  Не удалось создать CoinGecko клиент: {e}")
        
        try:
            clients["exchangerate"] = ExchangeRateApiClient(config)
        except Exception as e:
            print(f"⚠️  Не удалось создать ExchangeRate клиент: {e}")
        
        return clients