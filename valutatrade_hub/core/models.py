# valutatrade_hub/core/models.py
import json
import hashlib
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field, asdict

from .exceptions import InsufficientFundsError, InvalidAmountError
from .currencies import Currency, CurrencyRegistry
from ..infra.database import DatabaseManager
from ..decorators import log_action


@dataclass
class Transaction:
    """Класс транзакции"""
    transaction_id: int
    user_id: int
    type: str  # 'buy', 'sell', 'deposit', 'withdraw', 'transfer'
    from_currency: Optional[str]
    to_currency: Optional[str]
    amount: Decimal
    rate: Optional[Decimal]
    fee: Optional[Decimal] = None
    description: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь для сериализации"""
        data = asdict(self)
        data['amount'] = str(self.amount)
        if self.rate:
            data['rate'] = str(self.rate)
        if self.fee:
            data['fee'] = str(self.fee)
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Создать из словаря"""
        return cls(
            transaction_id=data["transaction_id"],
            user_id=data["user_id"],
            type=data["type"],
            from_currency=data.get("from_currency"),
            to_currency=data.get("to_currency"),
            amount=Decimal(data["amount"]),
            rate=Decimal(data["rate"]) if data.get("rate") else None,
            fee=Decimal(data["fee"]) if data.get("fee") else None,
            description=data.get("description"),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


class User:
    """Класс пользователя системы"""
    
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
        email: Optional[str] = None,
        is_active: bool = True,
        login_attempts: int = 0,
        last_login: Optional[datetime] = None
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._salt = salt
        self._registration_date = registration_date
        self._email = email
        self._is_active = is_active
        self._login_attempts = login_attempts
        self._last_login = last_login
    
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
        if len(value.strip()) < 3:
            raise ValueError("Имя пользователя должно содержать минимум 3 символа")
        self._username = value
    
    @property
    def email(self) -> Optional[str]:
        return self._email
    
    @email.setter
    def email(self, value: Optional[str]):
        if value and '@' not in value:
            raise ValueError("Некорректный email адрес")
        self._email = value
    
    @property
    def registration_date(self) -> datetime:
        return self._registration_date
    
    @property
    def is_active(self) -> bool:
        return self._is_active
    
    @is_active.setter
    def is_active(self, value: bool):
        self._is_active = value
    
    @property
    def last_login(self) -> Optional[datetime]:
        return self._last_login
    
    @last_login.setter
    def last_login(self, value: Optional[datetime]):
        self._last_login = value
    
    def get_user_info(self) -> str:
        """Получить информацию о пользователе"""
        info = [
            f"ID: {self._user_id}",
            f"Имя: {self._username}",
            f"Дата регистрации: {self._registration_date.strftime('%Y-%m-%d %H:%M')}",
            f"Статус: {'Активен' if self._is_active else 'Неактивен'}"
        ]
        
        if self._email:
            info.append(f"Email: {self._email}")
        
        if self._last_login:
            info.append(f"Последний вход: {self._last_login.strftime('%Y-%m-%d %H:%M')}")
        
        return "\n".join(info)
    
    def change_password(self, new_password: str) -> None:
        """Изменить пароль пользователя"""
        if len(new_password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")
        
        self._salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(new_password)
    
    def verify_password(self, password: str) -> bool:
        """Проверить пароль"""
        return self._hashed_password == self._hash_password(password)
    
    def _hash_password(self, password: str) -> str:
        """Хеширование пароля с солью"""
        return hashlib.sha256(
            (password + self._salt).encode()
        ).hexdigest()
    
    def increment_login_attempts(self) -> None:
        """Увеличить счетчик неудачных попыток входа"""
        self._login_attempts += 1
    
    def reset_login_attempts(self) -> None:
        """Сбросить счетчик неудачных попыток входа"""
        self._login_attempts = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертировать в словарь для JSON"""
        return {
            "user_id": self._user_id,
            "username": self._username,
            "hashed_password": self._hashed_password,
            "salt": self._salt,
            "registration_date": self._registration_date.isoformat(),
            "email": self._email,
            "is_active": self._is_active,
            "login_attempts": self._login_attempts,
            "last_login": self._last_login.isoformat() if self._last_login else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        """Создать пользователя из словаря"""
        last_login = None
        if data.get("last_login"):
            last_login = datetime.fromisoformat(data["last_login"])
        
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            hashed_password=data["hashed_password"],
            salt=data["salt"],
            registration_date=datetime.fromisoformat(data["registration_date"]),
            email=data.get("email"),
            is_active=data.get("is_active", True),
            login_attempts=data.get("login_attempts", 0),
            last_login=last_login
        )


class Wallet:
    """Класс кошелька для одной валюты"""
    
    def __init__(self, currency_code: str, balance: Decimal = Decimal('0.0')):
        self._currency = CurrencyRegistry.get_currency(currency_code)
        self._balance = balance
    
    @property
    def currency_code(self) -> str:
        return self._currency.code
    
    @property
    def currency(self) -> Currency:
        return self._currency
    
    @property
    def balance(self) -> Decimal:
        return self._balance
    
    @balance.setter
    def balance(self, value: Decimal):
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        
        if value < Decimal('0'):
            raise ValueError("Баланс не может быть отрицательным")
        
        self._balance = value
    
    @log_action(include_args=True, include_result=True)
    def deposit(self, amount: Decimal) -> None:
        """Пополнить баланс"""
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        if amount <= Decimal('0'):
            raise InvalidAmountError(float(amount))
        
        self.balance += amount
    
    @log_action(include_args=True, include_result=True)
    def withdraw(self, amount: Decimal) -> Decimal:
        """Снять средства с баланса"""
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        if amount <= Decimal('0'):
            raise InvalidAmountError(float(amount))
        
        if amount > self._balance:
            raise InsufficientFundsError(
                self.currency_code,
                float(self._balance),
                float(amount)
            )
        
        self.balance -= amount
        return amount
    
    def get_balance_info(self) -> str:
        """Получить информацию о балансе"""
        currency_info = self._currency.get_display_info()
        return f"{currency_info} - Баланс: {self._balance:.8f}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "currency_code": self.currency_code,
            "balance": str(self._balance)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Wallet':
        return cls(
            currency_code=data["currency_code"],
            balance=Decimal(data["balance"])
        )


class Portfolio:
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
    
    @log_action(include_args=True, include_result=True)
    def add_currency(self, currency_code: str) -> Wallet:
        """Добавить новую валюту в портфель"""
        currency_code = currency_code.upper()
        
        if currency_code in self._wallets:
            raise ValueError(f"Валюта {currency_code} уже есть в портфеле")
        
        wallet = Wallet(currency_code)
        self._wallets[currency_code] = wallet
        return wallet
    
    def get_wallet(self, currency_code: str) -> Optional[Wallet]:
        """Получить кошелек по коду валюты"""
        return self._wallets.get(currency_code.upper())
    
    def has_wallet(self, currency_code: str) -> bool:
        """Проверить наличие кошелька"""
        return currency_code.upper() in self._wallets
    
    def get_total_value(self, base_currency: str = 'USD') -> Decimal:
        """Получить общую стоимость портфеля в базовой валюте"""
        total = Decimal('0')
        
        for currency_code, wallet in self._wallets.items():
            if currency_code == base_currency:
                total += wallet.balance
            else:
                # Здесь будет интеграция с ExchangeRateService
                # Пока возвращаем просто баланс
                total += wallet.balance
        
        return total
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self._user_id,
            "wallets": {
                code: wallet.to_dict()
                for code, wallet in self._wallets.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Portfolio':
        wallets = {}
        for code, wallet_data in data.get("wallets", {}).items():
            wallets[code] = Wallet.from_dict(wallet_data)
        
        return cls(
            user_id=data["user_id"],
            wallets=wallets
        )