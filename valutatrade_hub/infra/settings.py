# valutatrade_hub/infra/settings.py
import os
import yaml
from typing import Any, Dict, Optional
from pathlib import Path
from ..core.exceptions import ConfigError


class SingletonMeta(type):
    """
    Метакласс для реализации паттерна Singleton.
    Гарантирует, что класс имеет только один экземпляр.
    """
    
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class SettingsLoader(metaclass=SingletonMeta):
    """
    Загрузчик настроек приложения.
    Singleton для гарантии единой точки доступа к конфигурации.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Инициализация загрузчика настроек"""
        if hasattr(self, '_initialized'):
            return  # Уже инициализирован
        
        self._config: Dict[str, Any] = {}
        self._config_path = config_path or self._find_config_path()
        self._load_config()
        self._set_defaults()
        self._initialized = True
    
    def _find_config_path(self) -> str:
        """Найти путь к конфигурационному файлу"""
        possible_paths = [
            "config/config.yaml",
            "config/config.yml",
            "valutatrade_hub/config.yaml",
            "valutatrade_hub/config.yml",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Создаем дефолтный конфиг, если файл не найден
        return "config/config.yaml"
    
    def _load_config(self) -> None:
        """Загрузить конфигурацию из файла"""
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f) or {}
            else:
                self._config = {}
                self._create_default_config()
        except yaml.YAMLError as e:
            raise ConfigError(f"Ошибка парсинга YAML: {e}")
        except Exception as e:
            raise ConfigError(f"Ошибка загрузки конфигурации: {e}")
    
    def _create_default_config(self) -> None:
        """Создать конфигурацию по умолчанию"""
        default_config = {
            'app': {
                'name': 'ValutaTrade Hub',
                'version': '1.0.0',
                'debug': False,
            },
            'paths': {
                'data_dir': 'data',
                'logs_dir': 'logs',
                'users_file': 'data/users.json',
                'portfolios_file': 'data/portfolios.json',
                'rates_file': 'data/rates.json',
                'transactions_file': 'data/transactions.json',
                'currencies_file': 'data/currencies.json',
            },
            'rates': {
                'ttl_seconds': 300,  # 5 минут
                'default_base_currency': 'USD',
                'update_on_start': True,
                'max_retries': 3,
                'retry_delay': 1,
            },
            'trading': {
                'min_trade_amount': 0.00000001,
                'default_fee_percent': 0.1,
                'enable_margin_trading': False,
                'max_leverage': 1.0,
            },
            'logging': {
                'level': 'INFO',
                'format': 'json',  # json или text
                'file': 'logs/valutatrade.log',
                'max_size_mb': 10,
                'backup_count': 5,
                'enable_console': True,
                'enable_file': True,
            },
            'security': {
                'password_min_length': 4,
                'session_timeout_minutes': 30,
                'max_login_attempts': 5,
                'enable_2fa': False,
            },
            'api': {
                'exchange_rates_api': 'https://api.exchangerate-api.com/v4/latest/USD',
                'crypto_api': 'https://api.coingecko.com/api/v3',
                'timeout_seconds': 10,
                'enable_caching': True,
                'cache_ttl_minutes': 5,
            }
        }
        
        # Создаем директории, если их нет
        os.makedirs('config', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        os.makedirs('logs', exist_ok=True)
        
        # Сохраняем конфиг по умолчанию
        with open(self._config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        
        self._config = default_config
    
    def _set_defaults(self) -> None:
        """Установить значения по умолчанию для отсутствующих ключей"""
        defaults = {
            'paths.data_dir': 'data',
            'rates.ttl_seconds': 300,
            'rates.default_base_currency': 'USD',
            'logging.level': 'INFO',
            'security.password_min_length': 4,
        }
        
        for key, default_value in defaults.items():
            keys = key.split('.')
            current = self._config
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            if keys[-1] not in current:
                current[keys[-1]] = default_value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Получить значение конфигурации по ключу.
        
        Args:
            key: Ключ в формате 'section.subsection.key'
            default: Значение по умолчанию, если ключ не найден
        
        Returns:
            Значение конфигурации или default
        """
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Установить значение конфигурации"""
        keys = key.split('.')
        current = self._config
        
        for k in keys[:-1]:
            current = current.setdefault(k, {})
        
        current[keys[-1]] = value
    
    def reload(self) -> None:
        """Перезагрузить конфигурацию из файла"""
        self._load_config()
    
    def save(self) -> None:
        """Сохранить текущую конфигурацию в файл"""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            raise ConfigError(f"Ошибка сохранения конфигурации: {e}")
    
    def get_all(self) -> Dict[str, Any]:
        """Получить всю конфигурацию"""
        return self._config.copy()
    
    def get_data_path(self, filename: str) -> str:
        """Получить полный путь к файлу данных"""
        data_dir = self.get('paths.data_dir', 'data')
        return os.path.join(data_dir, filename)
    
    def get_rates_ttl(self) -> int:
        """Получить TTL курсов в секундах"""
        return self.get('rates.ttl_seconds', 300)
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Получить конфигурацию логирования"""
        return self.get('logging', {})
    def get_currency_precision(self) -> Dict[str, int]:
        """Получить точность отображения для валют"""
        precision_str = self.get('tool.valutatrade.currency_precision', '')
        if not precision_str:
            return {}
        
        # Преобразуем строку "USD: 2, EUR: 2" в словарь
        result = {}
        pairs = [pair.strip() for pair in precision_str.split(',')]
        for pair in pairs:
            if ':' in pair:
                currency, value = pair.split(':', 1)
                result[currency.strip()] = int(value.strip())
        
        return result
    
    def get_fiat_issuing_countries(self) -> Dict[str, str]:
        """Получить страны эмитенты для фиатных валют"""
        countries_str = self.get('tool.valutatrade.fiat_issuing_countries', '')
        if not countries_str:
            return {}
        
        result = {}
        pairs = [pair.strip() for pair in countries_str.split(',')]
        for pair in pairs:
            if ':' in pair:
                currency, country = pair.split(':', 1)
                result[currency.strip()] = country.strip()
        
        return result
    
    def get_crypto_algorithms(self) -> Dict[str, str]:
        """Получить алгоритмы для криптовалют"""
        algorithms_str = self.get('tool.valutatrade.crypto_algorithms', '')
        if not algorithms_str:
            return {}
        
        result = {}
        pairs = [pair.strip() for pair in algorithms_str.split(',')]
        for pair in pairs:
            if ':' in pair:
                currency, algorithm = pair.split(':', 1)
                result[currency.strip()] = algorithm.strip()
        
        return result
    
    def get_initial_rates(self) -> Dict[str, float]:
        """Получить начальные курсы"""
        rates_str = self.get('tool.valutatrade.initial_rates', '')
        if not rates_str:
            return {}
        
        result = {}
        pairs = [pair.strip() for pair in rates_str.split(',')]
        for pair in pairs:
            if ':' in pair:
                pair_key, rate = pair.split(':', 1)
                result[pair_key.strip()] = float(rate.strip())
        
        return result
    
    def get_cli_colors(self) -> Dict[str, str]:
        """Получить цветовую схему CLI"""
        colors_str = self.get('tool.valutatrade.cli_colors', '')
        if not colors_str:
            return {}
        
        result = {}
        pairs = [pair.strip() for pair in colors_str.split(',')]
        for pair in pairs:
            if ':' in pair:
                element, color = pair.split(':', 1)
                result[element.strip()] = color.strip()
        
        return result