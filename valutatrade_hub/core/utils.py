# valutatrade_hub/core/utils.py
import hashlib
import json
import os
import re
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class JSONFileManager:
    """Менеджер для работы с JSON файлами"""
    
    @staticmethod
    def load_data(filepath: str) -> Any:
        try:
            if not os.path.exists(filepath):
                return [] if any(x in filepath for x in ["users", "portfolios", "transactions"]) else {}
            
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return [] if any(x in filepath for x in ["users", "portfolios", "transactions"]) else {}
    
    @staticmethod
    def save_data(filepath: str, data: Any) -> None:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=default_serializer, ensure_ascii=False)


class PasswordHasher:
    """Класс для хеширования паролей"""
    
    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Простой псевдо-хеш для демонстрации
        hashed = hashlib.sha256((password + salt).encode()).hexdigest()
        return hashed, salt
    
    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        test_hash, _ = PasswordHasher.hash_password(password, salt)
        return test_hash == hashed_password


class CurrencyValidator:
    """Валидатор валютных операций"""
    
    @staticmethod
    def validate_currency_code(code: str) -> bool:
        """
        Проверить валидность кода валюты через реестр валют
        
        Args:
            code: код валюты для проверки
        
        Returns:
            True если валюта найдена в реестре, False иначе
        """
        if not isinstance(code, str):
            return False
        
        try:
            from .currencies import get_currency
            get_currency(code)
            return True
        except Exception:
            return False
    
    @staticmethod
    def validate_amount(amount_str: str) -> Decimal:
        """Проверить и преобразовать сумму"""
        try:
            amount = Decimal(amount_str)
            if amount <= Decimal('0'):
                raise ValueError("Сумма должна быть положительной")
            return amount
        except (InvalidOperation, ValueError) as e:
            raise ValueError(f"Некорректная сумма: {amount_str}") from e
    
    @staticmethod
    def validate_username(username: str) -> bool:
        return bool(username and len(username) >= 3 and re.match(r'^[a-zA-Z0-9_]+$', username))
    
    @staticmethod
    def validate_password(password: str) -> bool:
        return len(password) >= 4


class CLIFormatter:
    """Форматирование вывода для CLI"""
    
    @staticmethod
    def format_currency(amount: Decimal, currency: str) -> str:
        if currency in ['BTC', 'ETH']:
            return f"{amount:.8f} {currency}"
        else:
            return f"{amount:.2f} {currency}"
    
    @staticmethod
    def format_rate(rate: Decimal, from_currency: str, to_currency: str) -> str:
        if rate < Decimal('0.001'):
            return f"1 {from_currency} = {rate:.8f} {to_currency}"
        elif rate < Decimal('1'):
            return f"1 {from_currency} = {rate:.4f} {to_currency}"
        else:
            return f"1 {from_currency} = {rate:.2f} {to_currency}"