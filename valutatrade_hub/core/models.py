# valutatrade_hub/core/models.py
import json
import hashlib
import secrets
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


class Serializable(ABC):
    """Абстрактный базовый класс для сериализуемых объектов"""

    @abstractmethod
    def to_dict(self) -> dict:
        """Конвертировать объект в словарь для сериализации"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict):
        """Создать объект из словаря"""
        pass


class User(Serializable):
    """Класс пользователя системы"""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str):
        if not value or not isinstance(value, str):
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> str:
        """Получить информацию о пользователе"""
        return (
            f"ID: {self._user_id}\n"
            f"Имя: {self._username}\n"
            f"Дата регистрации: {self._registration_date}"
        )

    def change_password(self, new_password: str) -> None:
        """Изменить пароль пользователя"""
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        # Генерируем новую соль и хешируем пароль
        self._salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(new_password)

    def verify_password(self, password: str) -> bool:
        """Проверить пароль"""
        return self._hashed_password == self._hash_password(password)

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля с солью"""
        return hashlib.sha256((password + self._salt).encode()).hexdigest()

    def to_dict(self) -> dict:
        """Конвертировать в словарь для JSON"""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Создать пользователя из словаря"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet(Serializable):
    """Класс кошелька для одной валюты"""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self._balance = balance

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float):
        if not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополнить баланс"""
        if amount <= 0:
            raise ValueError("Сумма пополнения должна быть положительной")
        self.balance += amount

    def withdraw(self, amount: float) -> bool:
        """Снять средства с баланса"""
        if amount <= 0:
            raise ValueError("Сумма снятия должна быть положительной")
        if amount > self._balance:
            return False

        self.balance -= amount
        return True

    def get_balance_info(self) -> str:
        """Получить информацию о балансе"""
        return f"{self.currency_code}: {self._balance:.2f}"

    def to_dict(self) -> dict:
        return {"currency_code": self.currency_code, "balance": self._balance}

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(currency_code=data["currency_code"], balance=data["balance"])


class Portfolio(Serializable):
    """Класс портфеля пользователя"""

    def __init__(self, user_id: int, wallets: Optional[Dict[str, Wallet]] = None):
        self._user_id = user_id
        self._wallets = wallets or {}

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def wallets(self) -> Dict[str, Wallet]:
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> None:
        """Добавить новую валюту в портфель"""
        if currency_code in self._wallets:
            raise ValueError(f"Валюта {currency_code} уже есть в портфеле")

        self._wallets[currency_code] = Wallet(currency_code)

    def get_wallet(self, currency_code: str) -> Optional[Wallet]:
        """Получить кошелек по коду валюты"""
        return self._wallets.get(currency_code)

    def get_total_value(self, base_currency: str = "USD") -> float:
        """Получить общую стоимость портфеля в базовой валюте"""
        # Фиктивные курсы для примера
        exchange_rates = {"USD": 1.0, "EUR": 1.2, "BTC": 50000.0, "ETH": 3000.0}

        total = 0.0
        for currency, wallet in self._wallets.items():
            rate = exchange_rates.get(currency, 1.0)
            base_rate = exchange_rates.get(base_currency, 1.0)
            total += (wallet.balance * rate) / base_rate

        return total

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "wallets": {code: wallet.to_dict() for code, wallet in self._wallets.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        wallets = {}
        for code, wallet_data in data.get("wallets", {}).items():
            wallets[code] = Wallet.from_dict(wallet_data)

        return cls(user_id=data["user_id"], wallets=wallets)  # valutatrade_hub/core/models.py


import json
import hashlib
import secrets
from datetime import datetime
from typing import Dict, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


class Serializable(ABC):
    """Абстрактный базовый класс для сериализуемых объектов"""

    @abstractmethod
    def to_dict(self) -> dict:
        """Конвертировать объект в словарь для сериализации"""
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict):
        """Создать объект из словаря"""
        pass


class User(Serializable):
    """Класс пользователя системы"""

    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @username.setter
    def username(self, value: str):
        if not value or not isinstance(value, str):
            raise ValueError("Имя пользователя не может быть пустым")
        self._username = value

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    def get_user_info(self) -> str:
        """Получить информацию о пользователе"""
        return (
            f"ID: {self._user_id}\n"
            f"Имя: {self._username}\n"
            f"Дата регистрации: {self._registration_date}"
        )

    def change_password(self, new_password: str) -> None:
        """Изменить пароль пользователя"""
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        # Генерируем новую соль и хешируем пароль
        self._salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(new_password)

    def verify_password(self, password: str) -> bool:
        """Проверить пароль"""
        return self._hashed_password == self._hash_password(password)

    def _hash_password(self, password: str) -> str:
        """Хеширование пароля с солью"""
        return hashlib.sha256((password + self._salt).encode()).hexdigest()

    def to_dict(self) -> dict:
        """Конвертировать в словарь для JSON"""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Создать пользователя из словаря"""
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
        )


class Wallet(Serializable):
    """Класс кошелька для одной валюты"""

    def __init__(self, currency_code: str, balance: float = 0.0):
        self.currency_code = currency_code
        self._balance = balance

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, value: float):
        if not isinstance(value, (int, float)):
            raise TypeError("Баланс должен быть числом")
        if value < 0:
            raise ValueError("Баланс не может быть отрицательным")
        self._balance = float(value)

    def deposit(self, amount: float) -> None:
        """Пополнить баланс"""
        if amount <= 0:
            raise ValueError("Сумма пополнения должна быть положительной")
        self.balance += amount

    def withdraw(self, amount: float) -> bool:
        """Снять средства с баланса"""
        if amount <= 0:
            raise ValueError("Сумма снятия должна быть положительной")
        if amount > self._balance:
            return False

        self.balance -= amount
        return True

    def get_balance_info(self) -> str:
        """Получить информацию о балансе"""
        return f"{self.currency_code}: {self._balance:.2f}"

    def to_dict(self) -> dict:
        return {"currency_code": self.currency_code, "balance": self._balance}

    @classmethod
    def from_dict(cls, data: dict) -> "Wallet":
        return cls(currency_code=data["currency_code"], balance=data["balance"])


class Portfolio(Serializable):
    """Класс портфеля пользователя"""

    def __init__(self, user_id: int, wallets: Optional[Dict[str, Wallet]] = None):
        self._user_id = user_id
        self._wallets = wallets or {}

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def wallets(self) -> Dict[str, Wallet]:
        return self._wallets.copy()

    def add_currency(self, currency_code: str) -> None:
        """Добавить новую валюту в портфель"""
        if currency_code in self._wallets:
            raise ValueError(f"Валюта {currency_code} уже есть в портфеле")

        self._wallets[currency_code] = Wallet(currency_code)

    def get_wallet(self, currency_code: str) -> Optional[Wallet]:
        """Получить кошелек по коду валюты"""
        return self._wallets.get(currency_code)

    def get_total_value(self, base_currency: str = "USD") -> float:
        """Получить общую стоимость портфеля в базовой валюте"""
        # Фиктивные курсы для примера
        exchange_rates = {"USD": 1.0, "EUR": 1.2, "BTC": 50000.0, "ETH": 3000.0}

        total = 0.0
        for currency, wallet in self._wallets.items():
            rate = exchange_rates.get(currency, 1.0)
            base_rate = exchange_rates.get(base_currency, 1.0)
            total += (wallet.balance * rate) / base_rate

        return total

    def to_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "wallets": {code: wallet.to_dict() for code, wallet in self._wallets.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Portfolio":
        wallets = {}
        for code, wallet_data in data.get("wallets", {}).items():
            wallets[code] = Wallet.from_dict(wallet_data)

        return cls(user_id=data["user_id"], wallets=wallets)
