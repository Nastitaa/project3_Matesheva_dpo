# valutatrade_hub/core/usecases.py
from typing import List, Optional, Dict
from datetime import datetime
import os
from .models import User, Portfolio, Wallet
from .utils import JSONFileManager, PasswordHasher


class UserManager:
    """Менеджер пользователей"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.users_file = os.path.join(data_dir, "users.json")
        self.users: Dict[int, User] = {}
        self._load_users()

    def _load_users(self) -> None:
        """Загрузить пользователей из файла"""
        data = JSONFileManager.load_data(self.users_file)
        for user_data in data:
            user = User.from_dict(user_data)
            self.users[user.user_id] = user

    def _save_users(self) -> None:
        """Сохранить пользователей в файл"""
        data = [user.to_dict() for user in self.users.values()]
        JSONFileManager.save_data(self.users_file, data)

    def register_user(self, username: str, password: str) -> User:
        """Зарегистрировать нового пользователя"""
        # Проверяем уникальность имени
        for user in self.users.values():
            if user.username == username:
                raise ValueError(f"Пользователь {username} уже существует")

        # Создаем нового пользователя
        user_id = max(self.users.keys(), default=0) + 1
        hashed_password, salt = PasswordHasher.hash_password(password)

        user = User(
            user_id=user_id,
            username=username,
            hashed_password=hashed_password,
            salt=salt,
            registration_date=datetime.now(),
        )

        self.users[user_id] = user
        self._save_users()
        return user

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Аутентифицировать пользователя"""
        for user in self.users.values():
            if user.username == username and user.verify_password(password):
                return user
        return None

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Получить пользователя по ID"""
        return self.users.get(user_id)


class PortfolioManager:
    """Менеджер портфелей"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.portfolios_file = os.path.join(data_dir, "portfolios.json")
        self.portfolios: Dict[int, Portfolio] = {}
        self._load_portfolios()

    def _load_portfolios(self) -> None:
        """Загрузить портфели из файла"""
        data = JSONFileManager.load_data(self.portfolios_file)
        for portfolio_data in data:
            portfolio = Portfolio.from_dict(portfolio_data)
            self.portfolios[portfolio.user_id] = portfolio

    def _save_portfolios(self) -> None:
        """Сохранить портфели в файл"""
        data = [portfolio.to_dict() for portfolio in self.portfolios.values()]
        JSONFileManager.save_data(self.portfolios_file, data)

    def get_user_portfolio(self, user_id: int) -> Portfolio:
        """Получить портфель пользователя"""
        if user_id not in self.portfolios:
            # Создаем новый портфель с USD по умолчанию
            portfolio = Portfolio(user_id)
            portfolio.add_currency("USD")
            self.portfolios[user_id] = portfolio
            self._save_portfolios()

        return self.portfolios[user_id]

    def execute_trade(
        self, user_id: int, from_currency: str, to_currency: str, amount: float, rate: float
    ) -> bool:
        """Выполнить обмен валюты"""
        portfolio = self.get_user_portfolio(user_id)

        from_wallet = portfolio.get_wallet(from_currency)
        to_wallet = portfolio.get_wallet(to_currency)

        if not from_wallet:
            raise ValueError(f"Нет кошелька для валюты {from_currency}")

        # Создаем кошелек для целевой валюты, если его нет
        if not to_wallet:
            portfolio.add_currency(to_currency)
            to_wallet = portfolio.get_wallet(to_currency)

        # Проверяем достаточно ли средств
        if from_wallet.balance < amount:
            return False

        # Выполняем обмен
        if from_wallet.withdraw(amount):
            to_wallet.deposit(amount * rate)
            self._save_portfolios()
            return True

        return False


class ExchangeRateService:
    """Сервис курсов валют"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.rates_file = os.path.join(data_dir, "rates.json")
        self.rates = JSONFileManager.load_data(self.rates_file)

        # Инициализируем фиктивные курсы, если файл пуст
        if not self.rates:
            self.rates = {
                "USD": {"EUR": 0.85, "GBP": 0.73, "JPY": 110.0, "BTC": 0.00002, "ETH": 0.0003},
                "EUR": {"USD": 1.18, "GBP": 0.86, "JPY": 129.0},
                "GBP": {"USD": 1.37, "EUR": 1.16, "JPY": 150.0},
                "JPY": {"USD": 0.0091, "EUR": 0.0078, "GBP": 0.0067},
                "BTC": {"USD": 50000.0, "EUR": 42500.0},
                "ETH": {"USD": 3000.0, "EUR": 2550.0},
            }
            self.save_rates()

    def save_rates(self) -> None:
        """Сохранить курсы в файл"""
        JSONFileManager.save_data(self.rates_file, self.rates)

    def get_rate(self, from_currency: str, to_currency: str) -> Optional[float]:
        """Получить курс обмена"""
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        if from_currency == to_currency:
            return 1.0

        if from_currency in self.rates and to_currency in self.rates[from_currency]:
            return self.rates[from_currency][to_currency]

        # Пробуем найти обратный курс
        if to_currency in self.rates and from_currency in self.rates[to_currency]:
            return 1.0 / self.rates[to_currency][from_currency]

        return None
