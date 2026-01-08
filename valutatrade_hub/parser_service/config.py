# valutatrade_hub/parser_service/config.py
"""
Конфигурация сервиса парсинга курсов валют.
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from pathlib import Path


@dataclass
class ParserConfig:
    """
    Конфигурация для сервиса парсинга курсов валют.
    Ключи API загружаются из переменных окружения для безопасности.
    """
    
    # API ключи (загружаются из переменных окружения)
    EXCHANGERATE_API_KEY: str = field(default_factory=lambda: os.getenv(
        "EXCHANGERATE_API_KEY", 
        "demo_key"  # Демо-ключ для тестирования
    ))
    
    # CoinGecko API (не требует ключа для бесплатного использования)
    COINGECKO_API_KEY: str = field(default_factory=lambda: os.getenv(
        "COINGECKO_API_KEY", 
        ""
    ))
    
    # Эндпоинты API
    COINGECKO_BASE_URL: str = "https://api.coingecko.com/api/v3"
    COINGECKO_SIMPLE_PRICE_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_BASE_URL: str = "https://v6.exchangerate-api.com/v6"
    
    # Базовые валюты
    BASE_FIAT_CURRENCY: str = "USD"
    BASE_CRYPTO_CURRENCY: str = "USD"
    
    # Списки отслеживаемых валют
    FIAT_CURRENCIES: Tuple[str, ...] = (
        "USD", "EUR", "GBP", "JPY", "RUB", 
        "CNY", "CHF", "CAD", "AUD"
    )
    
    CRYPTO_CURRENCIES: Tuple[str, ...] = (
        "BTC", "ETH", "BNB", "XRP", "ADA", 
        "SOL", "DOT"
    )
    
    # Сопоставление тикеров криптовалют с ID в CoinGecko
    CRYPTO_ID_MAP: Dict[str, str] = field(default_factory=lambda: {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "SOL": "solana",
        "DOT": "polkadot",
    })
    
    # Параметры запросов
    REQUEST_TIMEOUT: int = 15  # секунд
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2  # секунд
    
    # Параметры обновления
    UPDATE_INTERVAL_MINUTES: int = 5  # Интервал автоматического обновления
    CACHE_TTL_SECONDS: int = 300  # Время жизни кэша (5 минут)
    
    # Пути к файлам
    DATA_DIR: str = "data"
    RATES_FILE: str = "data/rates.json"  # Текущие курсы для Core Service
    EXCHANGE_RATES_FILE: str = "data/exchange_rates.json"  # Исторические данные
    PARSER_LOG_FILE: str = "logs/parser.log"
    
    # Настройки логирования
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json или text
    
    # Параметры для запросов к CoinGecko
    COINGECKO_REQUEST_DELAY: float = 1.0  # Задержка между запросами для избежания лимитов
    
    def __post_init__(self):
        """Проверка конфигурации после инициализации."""
        # Проверяем наличие API ключа для ExchangeRate-API
        if self.EXCHANGERATE_API_KEY == "demo_key":
            print("⚠️  Внимание: Используется демо-ключ ExchangeRate-API. "
                  "Для реального использования установите переменную окружения EXCHANGERATE_API_KEY.")
        
        # Проверяем сопоставление криптовалют
        missing_ids = []
        for crypto in self.CRYPTO_CURRENCIES:
            if crypto not in self.CRYPTO_ID_MAP:
                missing_ids.append(crypto)
        
        if missing_ids:
            print(f"⚠️  Внимание: Не найдены ID для криптовалют: {missing_ids}")
    
    @property
    def coingecko_ids_string(self) -> str:
        """Получить строку ID криптовалют для CoinGecko API."""
        ids = []
        for crypto in self.CRYPTO_CURRENCIES:
            if crypto in self.CRYPTO_ID_MAP:
                ids.append(self.CRYPTO_ID_MAP[crypto])
        return ",".join(ids)
    
    @property
    def exchangerate_api_url(self) -> str:
        """Получить полный URL для ExchangeRate-API."""
        return f"{self.EXCHANGERATE_API_BASE_URL}/{self.EXCHANGERATE_API_KEY}/latest/{self.BASE_FIAT_CURRENCY}"
    
    @property
    def coingecko_simple_price_url(self) -> str:
        """Получить URL для CoinGecko Simple Price API."""
        ids = self.coingecko_ids_string
        vs_currencies = "usd"
        return f"{self.COINGECKO_SIMPLE_PRICE_URL}?ids={ids}&vs_currencies={vs_currencies}"
    
    def validate_config(self) -> List[str]:
        """Валидация конфигурации."""
        errors = []
        
        # Проверка API ключа
        if not self.EXCHANGERATE_API_KEY or self.EXCHANGERATE_API_KEY == "demo_key":
            errors.append(
                "Не установлен API ключ для ExchangeRate-API. "
                "Установите переменную окружения EXCHANGERATE_API_KEY."
            )
        
        # Проверка списков валют
        if not self.FIAT_CURRENCIES:
            errors.append("Список фиатных валют пуст.")
        
        if not self.CRYPTO_CURRENCIES:
            errors.append("Список криптовалют пуст.")
        
        # Проверка путей
        data_dir = Path(self.DATA_DIR)
        if not data_dir.exists():
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Не удалось создать директорию данных: {e}")
        
        return errors
    
    def get_rate_file_path(self) -> Path:
        """Получить путь к файлу с текущими курсами."""
        return Path(self.RATES_FILE)
    
    def get_exchange_rates_file_path(self) -> Path:
        """Получить путь к файлу с историческими данными."""
        return Path(self.EXCHANGE_RATES_FILE)
    
    def get_all_tracked_pairs(self) -> List[str]:
        """Получить список всех отслеживаемых пар валют."""
        pairs = []
        
        # Фиатные валюты к базовой валюте
        for currency in self.FIAT_CURRENCIES:
            if currency != self.BASE_FIAT_CURRENCY:
                pairs.append(f"{currency}_{self.BASE_FIAT_CURRENCY}")
        
        # Криптовалюты к базовой валюте
        for currency in self.CRYPTO_CURRENCIES:
            pairs.append(f"{currency}_{self.BASE_CRYPTO_CURRENCY}")
        
        return pairs