# valutatrade_hub/core/currencies.py
from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal
import re


class Currency(ABC):
    """Абстрактный базовый класс валюты"""
    
    def __init__(self, name: str, code: str):
        self._validate_name(name)
        self._validate_code(code)
        
        self._name = name
        self._code = code.upper()
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def code(self) -> str:
        return self._code
    
    def _validate_name(self, name: str) -> None:
        """Валидация имени валюты"""
        if not name or not isinstance(name, str):
            raise ValueError("Имя валюты не может быть пустым")
        if len(name.strip()) < 2:
            raise ValueError("Имя валюты должно содержать минимум 2 символа")
    
    def _validate_code(self, code: str) -> None:
        """Валидация кода валюты"""
        if not code or not isinstance(code, str):
            raise ValueError("Код валюты не может быть пустым")
        
        code_upper = code.upper()
        if not re.match(r'^[A-Z]{2,5}$', code_upper):
            raise ValueError(
                f"Некорректный код валюты: {code}. "
                f"Код должен содержать 2-5 заглавных букв без пробелов"
            )
    
    @abstractmethod
    def get_display_info(self) -> str:
        """Получить строковое представление валюты для UI/логов"""
        pass
    
    def __str__(self) -> str:
        return self.get_display_info()
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self._name}', code='{self._code}')"
    
    def __eq__(self, other) -> bool:
        if not isinstance(other, Currency):
            return False
        return self._code == other.code
    
    def __hash__(self) -> int:
        return hash(self._code)


class FiatCurrency(Currency):
    """Класс фиатной валюты"""
    
    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self._issuing_country = issuing_country
    
    @property
    def issuing_country(self) -> str:
        return self._issuing_country
    
    def get_display_info(self) -> str:
        """Получить информацию о фиатной валюте"""
        return f"[FIAT] {self._code} — {self._name} (Issuing: {self._issuing_country})"


class CryptoCurrency(Currency):
    """Класс криптовалюты"""
    
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float = 0.0):
        super().__init__(name, code)
        self._algorithm = algorithm
        self._market_cap = market_cap
    
    @property
    def algorithm(self) -> str:
        return self._algorithm
    
    @property
    def market_cap(self) -> float:
        return self._market_cap
    
    @market_cap.setter
    def market_cap(self, value: float):
        if value < 0:
            raise ValueError("Рыночная капитализация не может быть отрицательной")
        self._market_cap = value
    
    def get_display_info(self) -> str:
        """Получить информацию о криптовалюте"""
        mcap_str = f"{self._market_cap:.2e}" if self._market_cap > 1e9 else f"{self._market_cap:,.0f}"
        return f"[CRYPTO] {self._code} — {self._name} (Algo: {self._algorithm}, MCAP: {mcap_str})"


class CurrencyRegistry:
    """Реестр валют с фабричным методом"""
    
    # Стандартные фиатные валюты
    _FIAT_CURRENCIES = {
        'USD': FiatCurrency("US Dollar", "USD", "United States"),
        'EUR': FiatCurrency("Euro", "EUR", "Eurozone"),
        'GBP': FiatCurrency("British Pound", "GBP", "United Kingdom"),
        'JPY': FiatCurrency("Japanese Yen", "JPY", "Japan"),
        'RUB': FiatCurrency("Russian Ruble", "RUB", "Russia"),
        'CNY': FiatCurrency("Chinese Yuan", "CNY", "China"),
        'CHF': FiatCurrency("Swiss Franc", "CHF", "Switzerland"),
        'CAD': FiatCurrency("Canadian Dollar", "CAD", "Canada"),
        'AUD': FiatCurrency("Australian Dollar", "AUD", "Australia"),
    }
    
    # Криптовалюты
    _CRYPTO_CURRENCIES = {
        'BTC': CryptoCurrency("Bitcoin", "BTC", "SHA-256", market_cap=1.12e12),
        'ETH': CryptoCurrency("Ethereum", "ETH", "Ethash", market_cap=3.8e11),
        'BNB': CryptoCurrency("Binance Coin", "BNB", "BEP-20", market_cap=8.5e10),
        'XRP': CryptoCurrency("Ripple", "XRP", "XRP Ledger", market_cap=4.2e10),
        'ADA': CryptoCurrency("Cardano", "ADA", "Ouroboros", market_cap=1.5e10),
        'SOL': CryptoCurrency("Solana", "SOL", "Proof of History", market_cap=3.2e10),
        'DOT': CryptoCurrency("Polkadot", "DOT", "Nominated Proof-of-Stake", market_cap=9.8e9),
    }
    
    @classmethod
    def get_all_currencies(cls) -> Dict[str, Currency]:
        """Получить все зарегистрированные валюты"""
        all_currencies = {}
        all_currencies.update(cls._FIAT_CURRENCIES)
        all_currencies.update(cls._CRYPTO_CURRENCIES)
        return all_currencies
    
    @classmethod
    def get_currency(cls, code: str) -> Currency:
        """Получить валюту по коду"""
        from ..core.exceptions import CurrencyNotFoundError
        
        code = code.upper()
        all_currencies = cls.get_all_currencies()
        
        if code not in all_currencies:
            raise CurrencyNotFoundError(f"Неизвестная валюта '{code}'")
        
        return all_currencies[code]
    
    @classmethod
    def register_currency(cls, currency: Currency) -> None:
        """Зарегистрировать новую валюту"""
        from ..core.exceptions import CurrencyRegistrationError
        
        if currency.code in cls.get_all_currencies():
            raise CurrencyRegistrationError(
                f"Валюта с кодом '{currency.code}' уже зарегистрирована"
            )
        
        if isinstance(currency, FiatCurrency):
            cls._FIAT_CURRENCIES[currency.code] = currency
        elif isinstance(currency, CryptoCurrency):
            cls._CRYPTO_CURRENCIES[currency.code] = currency
        else:
            raise CurrencyRegistrationError(
                f"Неизвестный тип валюты: {type(currency).__name__}"
            )
    
    @classmethod
    def get_supported_currencies(cls) -> Dict[str, str]:
        """Получить список поддерживаемых валют"""
        supported = {}
        for code, currency in cls.get_all_currencies().items():
            if isinstance(currency, FiatCurrency):
                supported[code] = f"FIAT - {currency.name}"
            else:
                supported[code] = f"CRYPTO - {currency.name}"
        return supported