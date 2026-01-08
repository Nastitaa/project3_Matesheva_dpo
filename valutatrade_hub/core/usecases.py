# valutatrade_hub/core/usecases.py
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Optional, List, Tuple, Any
from dataclasses import dataclass

from .models import User, Portfolio, Wallet, Transaction
from .currencies import Currency, CurrencyRegistry, FiatCurrency, CryptoCurrency
from .exceptions import (
    InsufficientFundsError,
    CurrencyNotFoundError,
    ApiRequestError,
    AuthenticationError,
    UserAlreadyExistsError,
    InvalidAmountError,
    DatabaseError
)
from .utils import CurrencyValidator, CLIFormatter
from ..infra.database import DatabaseManager
from ..infra.settings import SettingsLoader
from ..decorators import log_action, retry_on_exception, cache_result, measure_performance


@dataclass
class TradeResult:
    """Результат торговой операции"""
    success: bool
    transaction: Transaction
    amount: Decimal
    rate: Decimal
    fee: Decimal
    total_cost: Decimal
    old_balances: Dict[str, Decimal]
    new_balances: Dict[str, Decimal]
    message: str


class UserManager:
    """Менеджер пользователей"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.settings = SettingsLoader()
        self.users_file = self.settings.get('paths.users_file', 'users.json')
    
    @log_action(level=20, include_args=True, include_result=True)
    def register_user(
        self,
        username: str,
        password: str,
        email: Optional[str] = None
    ) -> User:
        """Зарегистрировать нового пользователя"""
        # Проверка уникальности имени
        existing_user = self.db.find_one(
            self.users_file,
            lambda u: u.get("username") == username
        )
        
        if existing_user:
            raise UserAlreadyExistsError(username)
        
        # Проверка пароля
        min_length = self.settings.get('security.password_min_length', 4)
        if len(password) < min_length:
            raise ValueError(f"Пароль должен быть не короче {min_length} символов")
        
        # Создание нового пользователя
        users = self.db.read_data(self.users_file, use_cache=False)
        user_id = max([u.get("user_id", 0) for u in users], default=0) + 1
        
        # Хеширование пароля
        salt = os.urandom(16).hex()
        hashed_password = self._hash_password(password, salt)
        
        user = User(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=datetime.now(),
            email=email
        )
        
        # Сохранение пользователя
        self.db.insert(self.users_file, user.to_dict())
        
        # Создание портфеля для пользователя
        portfolio_manager = PortfolioManager()
        portfolio_manager.get_user_portfolio(user_id)  # Создаст портфель по умолчанию
        
        return user
    
    @log_action(level=20, include_args=True, include_result=True)
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Аутентифицировать пользователя"""
        user_data = self.db.find_one(
            self.users_file,
            lambda u: u.get("username") == username
        )
        
        if not user_data:
            return None
        
        user = User.from_dict(user_data)
        
        # Проверка активности пользователя
        if not user.is_active:
            raise AuthenticationError("Пользователь заблокирован")
        
        # Проверка пароля
        if not user.verify_password(password):
            # Увеличиваем счетчик неудачных попыток
            user.increment_login_attempts()
            
            # Проверяем максимальное количество попыток
            max_attempts = self.settings.get('security.max_login_attempts', 5)
            if user.login_attempts >= max_attempts:
                user.is_active = False
            
            # Обновляем пользователя в базе
            self.db.update(
                self.users_file,
                lambda u: u.get("user_id") == user.user_id,
                lambda u: user.to_dict()
            )
            
            raise AuthenticationError("Неверный пароль")
        
        # Успешный вход - сбрасываем счетчик попыток
        user.reset_login_attempts()
        user.last_login = datetime.now()
        
        # Обновляем пользователя в базе
        self.db.update(
            self.users_file,
            lambda u: u.get("user_id") == user.user_id,
            lambda u: user.to_dict()
        )
        
        return user
    
    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        user_data = self.db.find_one(
            self.users_file,
            lambda u: u.get("user_id") == user_id
        )
        
        if not user_data:
            return None
        
        return User.from_dict(user_data)
    
    def _hash_password(self, password: str, salt: str) -> str:
        """Хеширование пароля"""
        import hashlib
        return hashlib.sha256((password + salt).encode()).hexdigest()


class PortfolioManager:
    """Менеджер портфелей"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.settings = SettingsLoader()
        self.portfolios_file = self.settings.get('paths.portfolios_file', 'portfolios.json')
    
    @log_action(include_args=True, include_result=True)
    def get_user_portfolio(self, user_id: int) -> Portfolio:
        """Получить портфель пользователя"""
        portfolio_data = self.db.find_one(
            self.portfolios_file,
            lambda p: p.get("user_id") == user_id
        )
        
        if portfolio_data:
            return Portfolio.from_dict(portfolio_data)
        
        # Создание нового портфеля
        portfolio = Portfolio(user_id)
        
        # Добавляем базовую валюту по умолчанию
        base_currency = self.settings.get('rates.default_base_currency', 'USD')
        portfolio.add_currency(base_currency)
        
        # Сохраняем портфель
        self.db.insert(self.portfolios_file, portfolio.to_dict())
        
        return portfolio
    
    @log_action(include_args=True, include_result=True)
    def save_portfolio(self, portfolio: Portfolio) -> None:
        """Сохранить портфель"""
        self.db.update(
            self.portfolios_file,
            lambda p: p.get("user_id") == portfolio.user_id,
            lambda p: portfolio.to_dict()
        )
    
    @log_action(include_args=True, include_result=True)
    def ensure_wallet_exists(self, user_id: int, currency_code: str) -> Wallet:
        """Убедиться, что кошелек существует (создать если нет)"""
        portfolio = self.get_user_portfolio(user_id)
        
        wallet = portfolio.get_wallet(currency_code)
        if not wallet:
            wallet = portfolio.add_currency(currency_code)
            self.save_portfolio(portfolio)
        
        return wallet


class ExchangeRateService:
    """Сервис курсов валют"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.settings = SettingsLoader()
        self.rates_file = self.settings.get('paths.rates_file', 'rates.json')
        self.rates_ttl = self.settings.get_rates_ttl()
        self._rates_cache: Dict[str, Dict] = {}
        self._cache_timestamp = 0
        
        # Загрузка курсов при инициализации
        self._load_rates()
    
    @log_action(include_args=True, include_result=True)
    def _load_rates(self) -> None:
        """Загрузить курсы из базы данных"""
        rates_data = self.db.read_data(self.rates_file)
        
        if not rates_data or not isinstance(rates_data, dict):
            # Инициализация начальными курсами
            self._initialize_rates()
        else:
            self._rates_cache = rates_data
        
        self._cache_timestamp = time.time()
    
    @log_action(level=20)
    def _initialize_rates(self) -> None:
        """Инициализировать начальные курсы"""
        now = datetime.now().isoformat()
        
        # Базовые курсы для основных пар
        self._rates_cache = {
            "rates": {
                "EUR_USD": {
                    "rate": 1.0786,
                    "updated_at": now,
                    "source": "initial"
                },
                "BTC_USD": {
                    "rate": 59337.21,
                    "updated_at": now,
                    "source": "initial"
                },
                "ETH_USD": {
                    "rate": 3720.00,
                    "updated_at": now,
                    "source": "initial"
                },
                "GBP_USD": {
                    "rate": 1.2634,
                    "updated_at": now,
                    "source": "initial"
                },
                "JPY_USD": {
                    "rate": 0.0068,
                    "updated_at": now,
                    "source": "initial"
                },
            },
            "metadata": {
                "last_refresh": now,
                "source": "initial",
                "base_currency": "USD"
            }
        }
        
        self._save_rates()
    
    @log_action(include_args=True, include_result=True)
    def _save_rates(self) -> None:
        """Сохранить курсы в базу данных"""
        self.db.write_data(self.rates_file, self._rates_cache)
        self._cache_timestamp = time.time()
    
    @retry_on_exception(max_retries=3, delay=1.0)
    @cache_result(ttl_seconds=60)  # Кэшируем результат на 60 секунд
    @measure_performance()
    @log_action(include_args=True, include_result=True)
    def get_rate(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Получить курс обмена
        
        Args:
            from_currency: Исходная валюта
            to_currency: Целевая валюта
        
        Returns:
            Курс обмена
        """
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()
        
        # Валидация валют
        try:
            CurrencyRegistry.get_currency(from_currency)
            CurrencyRegistry.get_currency(to_currency)
        except CurrencyNotFoundError as e:
            raise CurrencyNotFoundError(f"Одна из валют не найдена: {from_currency}, {to_currency}")
        
        if from_currency == to_currency:
            return Decimal('1.0')
        
        # Проверяем актуальность кэша
        if time.time() - self._cache_timestamp > self.rates_ttl:
            self._update_rates_from_api()
        
        # Ищем курс в кэше
        pair_key = f"{from_currency}_{to_currency}"
        reverse_key = f"{to_currency}_{from_currency}"
        
        rates = self._rates_cache.get("rates", {})
        
        # Прямой курс
        if pair_key in rates:
            rate_data = rates[pair_key]
            if self._is_rate_fresh(rate_data.get("updated_at")):
                return Decimal(str(rate_data["rate"]))
        
        # Обратный курс
        if reverse_key in rates:
            rate_data = rates[reverse_key]
            if self._is_rate_fresh(rate_data.get("updated_at")):
                return Decimal('1.0') / Decimal(str(rate_data["rate"]))
        
        # Если курс не найден или устарел, пытаемся получить из API
        rate = self._fetch_rate_from_api(from_currency, to_currency)
        self._update_rate_in_cache(pair_key, rate)
        
        return rate
    
    def _is_rate_fresh(self, updated_at: str) -> bool:
        """Проверить актуальность курса"""
        if not updated_at:
            return False
        
        try:
            updated_time = datetime.fromisoformat(updated_at)
            age = datetime.now() - updated_time
            return age.total_seconds() <= self.rates_ttl
        except:
            return False
    
    def _update_rates_from_api(self) -> None:
        """
        Обновить все курсы из API.
        Заглушка - в реальном приложении здесь будет запрос к внешнему API.
        """
        try:
            # Здесь должен быть реальный запрос к API
            # Для демонстрации просто обновляем время
            now = datetime.now().isoformat()
            
            # Обновляем метаданные
            self._rates_cache["metadata"]["last_refresh"] = now
            self._rates_cache["metadata"]["source"] = "api"
            
            # Симулируем обновление курсов (немного меняем значения)
            rates = self._rates_cache.get("rates", {})
            for key in rates:
                rate_data = rates[key]
                current_rate = Decimal(str(rate_data["rate"]))
                
                # Небольшое случайное изменение курса (±1%)
                import random
                change = Decimal(str(random.uniform(0.99, 1.01)))
                new_rate = current_rate * change
                
                rates[key] = {
                    "rate": float(new_rate),
                    "updated_at": now,
                    "source": "api"
                }
            
            self._save_rates()
            
        except Exception as e:
            raise ApiRequestError(f"Не удалось обновить курсы: {str(e)}")
    
    def _fetch_rate_from_api(self, from_currency: str, to_currency: str) -> Decimal:
        """
        Получить курс из API.
        Заглушка - возвращает фиктивные данные.
        """
        # Фиктивные курсы для демонстрации
        fake_rates = {
            "USD_EUR": Decimal('0.9271'),
            "USD_BTC": Decimal('0.00001685'),
            "USD_ETH": Decimal('0.0002688'),
            "USD_GBP": Decimal('0.7915'),
            "USD_JPY": Decimal('147.06'),
            "EUR_USD": Decimal('1.0786'),
            "BTC_USD": Decimal('59337.21'),
            "ETH_USD": Decimal('3720.00'),
            "EUR_BTC": Decimal('0.0000157'),
            "BTC_EUR": Decimal('63694.27'),
        }
        
        pair_key = f"{from_currency}_{to_currency}"
        
        if pair_key in fake_rates:
            return fake_rates[pair_key]
        
        # Если курс не найден, используем средний курс через USD
        try:
            usd_from = self.get_rate(from_currency, "USD")
            usd_to = self.get_rate("USD", to_currency)
            return usd_from * usd_to
        except:
            raise ApiRequestError(f"Не удалось получить курс для пары {from_currency}/{to_currency}")
    
    def _update_rate_in_cache(self, pair_key: str, rate: Decimal) -> None:
        """Обновить курс в кэше"""
        now = datetime.now().isoformat()
        
        if "rates" not in self._rates_cache:
            self._rates_cache["rates"] = {}
        
        self._rates_cache["rates"][pair_key] = {
            "rate": float(rate),
            "updated_at": now,
            "source": "calculated"
        }
        
        self._save_rates()
    
    @log_action(include_args=True, include_result=True)
    def get_all_rates(self, base_currency: str = "USD") -> Dict[str, Decimal]:
        """Получить все курсы относительно базовой валюты"""
        rates = {}
        
        # Получаем все поддерживаемые валюты
        all_currencies = CurrencyRegistry.get_all_currencies()
        
        for currency_code in all_currencies:
            if currency_code != base_currency:
                try:
                    rate = self.get_rate(base_currency, currency_code)
                    rates[currency_code] = rate
                except Exception as e:
                    # Пропускаем валюты с ошибками
                    continue
        
        return rates


class TransactionManager:
    """Менеджер транзакций"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.settings = SettingsLoader()
        self.transactions_file = self.settings.get('paths.transactions_file', 'transactions.json')
    
    @log_action(include_args=True, include_result=True)
    def create_transaction(self, **kwargs) -> Transaction:
        """Создать новую транзакцию"""
        # Получаем следующий ID
        transactions = self.db.read_data(self.transactions_file, use_cache=False)
        transaction_id = max([t.get("transaction_id", 0) for t in transactions], default=0) + 1
        
        # Создаем транзакцию
        transaction = Transaction(
            transaction_id=transaction_id,
            timestamp=datetime.now(),
            **kwargs
        )
        
        # Сохраняем транзакцию
        self.db.insert(self.transactions_file, transaction.to_dict())
        
        return transaction
    
    @log_action(include_args=True, include_result=True)
    def get_user_transactions(
        self,
        user_id: int,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Transaction]:
        """Получить транзакции пользователя"""
        transactions = self.db.read_data(self.transactions_file, use_cache=False)
        
        user_transactions = []
        for t in transactions:
            if t.get("user_id") == user_id:
                user_transactions.append(Transaction.from_dict(t))
        
        # Сортировка по времени (новые первыми)
        user_transactions.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Применяем пагинацию
        if offset:
            user_transactions = user_transactions[offset:]
        if limit:
            user_transactions = user_transactions[:limit]
        
        return user_transactions
    
    def get_transaction_summary(self, user_id: int) -> Dict[str, Any]:
        """Получить сводку по транзакциям пользователя"""
        transactions = self.get_user_transactions(user_id)
        
        summary = {
            "total_transactions": len(transactions),
            "total_buy": Decimal('0'),
            "total_sell": Decimal('0'),
            "total_deposit": Decimal('0'),
            "total_withdraw": Decimal('0'),
            "by_currency": {},
        }
        
        for t in transactions:
            if t.type == "buy":
                summary["total_buy"] += t.amount
            elif t.type == "sell":
                summary["total_sell"] += t.amount
            elif t.type == "deposit":
                summary["total_deposit"] += t.amount
            elif t.type == "withdraw":
                summary["total_withdraw"] += t.amount
            
            # Статистика по валютам
            currency = t.to_currency if t.type in ["buy", "deposit"] else t.from_currency
            if currency:
                if currency not in summary["by_currency"]:
                    summary["by_currency"][currency] = {
                        "buy": Decimal('0'),
                        "sell": Decimal('0'),
                        "deposit": Decimal('0'),
                        "withdraw": Decimal('0'),
                    }
                
                summary["by_currency"][currency][t.type] += t.amount
        
        return summary


class TradeService:
    """Сервис для выполнения торговых операций"""
    
    def __init__(self):
        self.portfolio_manager = PortfolioManager()
        self.exchange_service = ExchangeRateService()
        self.transaction_manager = TransactionManager()
        self.settings = SettingsLoader()
    
    @log_action(level=20, include_args=True, include_result=True, verbose=True)
    def buy_currency(
        self,
        user_id: int,
        currency: str,
        amount: Decimal,
        base_currency: str = "USD",
        fee_percent: Optional[float] = None
    ) -> TradeResult:
        """
        Купить валюту
        
        Args:
            user_id: ID пользователя
            currency: Код покупаемой валюты
            amount: Количество покупаемой валюты
            base_currency: Валюта для оплаты
            fee_percent: Комиссия в процентах
        
        Returns:
            Результат операции
        """
        # Валидация валют
        try:
            CurrencyRegistry.get_currency(currency)
            CurrencyRegistry.get_currency(base_currency)
        except CurrencyNotFoundError as e:
            raise
        
        # Валидация суммы
        if amount <= Decimal('0'):
            raise InvalidAmountError(float(amount))
        
        min_amount = Decimal(str(self.settings.get('trading.min_trade_amount', 0.00000001)))
        if amount < min_amount:
            raise InvalidAmountError(f"Минимальная сумма для покупки: {min_amount}")
        
        # Получаем курс
        rate = self.exchange_service.get_rate(base_currency, currency)
        
        # Рассчитываем стоимость и комиссию
        cost_in_base = amount * rate
        
        if fee_percent is None:
            fee_percent = self.settings.get('trading.default_fee_percent', 0.1)
        
        fee = cost_in_base * Decimal(str(fee_percent / 100))
        total_cost = cost_in_base + fee
        
        # Получаем портфель пользователя
        portfolio = self.portfolio_manager.get_user_portfolio(user_id)
        
        # Проверяем баланс в базовой валюте
        base_wallet = portfolio.get_wallet(base_currency)
        if not base_wallet:
            raise ValueError(f"Нет кошелька для базовой валюты {base_currency}")
        
        if base_wallet.balance < total_cost:
            raise InsufficientFundsError(
                base_currency,
                float(base_wallet.balance),
                float(total_cost)
            )
        
        # Получаем или создаем кошелек для покупаемой валюты
        currency_wallet = self.portfolio_manager.ensure_wallet_exists(user_id, currency)
        
        # Сохраняем старые балансы для логирования
        old_balances = {
            base_currency: base_wallet.balance,
            currency: currency_wallet.balance
        }
        
        try:
            # Атомарная операция покупки
            def execute_buy():
                # Списание с базового кошелька
                base_wallet.withdraw(total_cost)
                
                # Зачисление на целевой кошелек
                currency_wallet.deposit(amount)
                
                # Создаем запись о транзакции
                transaction = self.transaction_manager.create_transaction(
                    user_id=user_id,
                    type="buy",
                    from_currency=base_currency,
                    to_currency=currency,
                    amount=amount,
                    rate=rate,
                    fee=fee,
                    description=f"Покупка {amount} {currency} за {total_cost} {base_currency}"
                )
                
                # Сохраняем изменения
                self.portfolio_manager.save_portfolio(portfolio)
                
                return transaction
            
            transaction = self.portfolio_manager.db.update_data(
                self.portfolio_manager.portfolios_file,
                execute_buy
            )
            
            # Новые балансы
            new_balances = {
                base_currency: base_wallet.balance,
                currency: currency_wallet.balance
            }
            
            # Формируем сообщение об успехе
            message = (
                f"✅ Покупка выполнена успешно!\n"
                f"   Куплено: {CLIFormatter.format_currency(amount, currency)}\n"
                f"   По курсу: {CLIFormatter.format_rate(rate, base_currency, currency)}\n"
                f"   Стоимость: {CLIFormatter.format_currency(cost_in_base, base_currency)}\n"
                f"   Комиссия: {CLIFormatter.format_currency(fee, base_currency)}\n"
                f"   Итого: {CLIFormatter.format_currency(total_cost, base_currency)}"
            )
            
            return TradeResult(
                success=True,
                transaction=transaction,
                amount=amount,
                rate=rate,
                fee=fee,
                total_cost=total_cost,
                old_balances=old_balances,
                new_balances=new_balances,
                message=message
            )
            
        except Exception as e:
            # Логируем ошибку
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при покупке: {e}", extra={
                'user_id': user_id,
                'currency': currency,
                'amount': float(amount),
                'error': str(e)
            })
            raise
    
    @log_action(level=20, include_args=True, include_result=True, verbose=True)
    def sell_currency(
        self,
        user_id: int,
        currency: str,
        amount: Decimal,
        target_currency: str = "USD",
        fee_percent: Optional[float] = None
    ) -> TradeResult:
        """
        Продать валюту
        
        Args:
            user_id: ID пользователя
            currency: Код продаваемой валюты
            amount: Количество продаваемой валюты
            target_currency: Валюта для получения
            fee_percent: Комиссия в процентах
        
        Returns:
            Результат операции
        """
        # Валидация валют
        try:
            CurrencyRegistry.get_currency(currency)
            CurrencyRegistry.get_currency(target_currency)
        except CurrencyNotFoundError as e:
            raise
        
        # Валидация суммы
        if amount <= Decimal('0'):
            raise InvalidAmountError(float(amount))
        
        # Получаем курс
        rate = self.exchange_service.get_rate(currency, target_currency)
        
        # Рассчитываем выручку и комиссию
        revenue = amount * rate
        
        if fee_percent is None:
            fee_percent = self.settings.get('trading.default_fee_percent', 0.1)
        
        fee = revenue * Decimal(str(fee_percent / 100))
        net_revenue = revenue - fee
        
        # Получаем портфель пользователя
        portfolio = self.portfolio_manager.get_user_portfolio(user_id)
        
        # Проверяем баланс продаваемой валюты
        currency_wallet = portfolio.get_wallet(currency)
        if not currency_wallet:
            raise ValueError(f"У вас нет кошелька '{currency}'. "
                           f"Добавьте валюту: она создаётся автоматически при первой покупке.")
        
        if currency_wallet.balance < amount:
            raise InsufficientFundsError(
                currency,
                float(currency_wallet.balance),
                float(amount)
            )
        
        # Получаем или создаем кошелек для целевой валюты
        target_wallet = self.portfolio_manager.ensure_wallet_exists(user_id, target_currency)
        
        # Сохраняем старые балансы для логирования
        old_balances = {
            currency: currency_wallet.balance,
            target_currency: target_wallet.balance
        }
        
        try:
            # Атомарная операция продажи
            def execute_sell():
                # Списание с кошелька продаваемой валюты
                currency_wallet.withdraw(amount)
                
                # Зачисление на целевой кошелек
                target_wallet.deposit(net_revenue)
                
                # Создаем запись о транзакции
                transaction = self.transaction_manager.create_transaction(
                    user_id=user_id,
                    type="sell",
                    from_currency=currency,
                    to_currency=target_currency,
                    amount=amount,
                    rate=rate,
                    fee=fee,
                    description=f"Продажа {amount} {currency} за {net_revenue} {target_currency}"
                )
                
                # Сохраняем изменения
                self.portfolio_manager.save_portfolio(portfolio)
                
                return transaction
            
            transaction = self.portfolio_manager.db.update_data(
                self.portfolio_manager.portfolios_file,
                execute_sell
            )
            
            # Новые балансы
            new_balances = {
                currency: currency_wallet.balance,
                target_currency: target_wallet.balance
            }
            
            # Формируем сообщение об успехе
            message = (
                f"✅ Продажа выполнена успешно!\n"
                f"   Продано: {CLIFormatter.format_currency(amount, currency)}\n"
                f"   По курсу: {CLIFormatter.format_rate(rate, currency, target_currency)}\n"
                f"   Выручка: {CLIFormatter.format_currency(revenue, target_currency)}\n"
                f"   Комиссия: {CLIFormatter.format_currency(fee, target_currency)}\n"
                f"   Чистая выручка: {CLIFormatter.format_currency(net_revenue, target_currency)}"
            )
            
            return TradeResult(
                success=True,
                transaction=transaction,
                amount=amount,
                rate=rate,
                fee=fee,
                total_cost=net_revenue,
                old_balances=old_balances,
                new_balances=new_balances,
                message=message
            )
            
        except Exception as e:
            # Логируем ошибку
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка при продаже: {e}", extra={
                'user_id': user_id,
                'currency': currency,
                'amount': float(amount),
                'error': str(e)
            })
            raise
    
    @log_action(include_args=True, include_result=True)
    def get_portfolio_value(
        self,
        user_id: int,
        base_currency: str = "USD"
    ) -> Dict[str, Any]:
        """
        Получить стоимость портфеля
        
        Args:
            user_id: ID пользователя
            base_currency: Базовая валюта
        
        Returns:
            Информация о стоимости портфеля
        """
        portfolio = self.portfolio_manager.get_user_portfolio(user_id)
        
        total_value = Decimal('0')
        currency_values = {}
        
        for currency_code, wallet in portfolio.wallets.items():
            if currency_code == base_currency:
                value = wallet.balance
            else:
                try:
                    rate = self.exchange_service.get_rate(currency_code, base_currency)
                    value = wallet.balance * rate
                except (CurrencyNotFoundError, ApiRequestError):
                    # Если курс не найден, не учитываем эту валюту
                    continue
            
            currency_values[currency_code] = {
                'balance': wallet.balance,
                'value_in_base': value,
                'currency_info': wallet.currency.get_display_info()
            }
            total_value += value
        
        return {
            'total_value': total_value,
            'base_currency': base_currency,
            'currencies': currency_values
        }