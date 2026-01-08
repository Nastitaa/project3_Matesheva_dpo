# valutatrade_hub/core/utils.py
import json
import os
from typing import Any, Dict, List
from datetime import datetime
from decimal import Decimal
import hashlib
import secrets


class JSONFileManager:
    """Менеджер для работы с JSON файлами"""

    @staticmethod
    def load_data(filepath: str) -> Any:
        """Загрузить данные из JSON файла"""
        try:
            if not os.path.exists(filepath):
                return [] if "users" in filepath or "portfolios" in filepath else {}

            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return [] if "users" in filepath or "portfolios" in filepath else {}

    @staticmethod
    def save_data(filepath: str, data: Any) -> None:
        """Сохранить данные в JSON файл"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        # Функция для сериализации объектов
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=default_serializer, ensure_ascii=False)


class PasswordHasher:
    """Класс для хеширования паролей"""

    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple[str, str]:
        """Хешировать пароль с солью"""
        if salt is None:
            salt = secrets.token_hex(16)

        hashed = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000
        ).hex()

        return hashed, salt

    @staticmethod
    def verify_password(password: str, hashed_password: str, salt: str) -> bool:
        """Проверить пароль"""
        test_hash, _ = PasswordHasher.hash_password(password, salt)
        return test_hash == hashed_password


class CurrencyValidator:
    """Валидатор валютных операций"""

    SUPPORTED_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "BTC", "ETH"}

    @staticmethod
    def validate_currency_code(code: str) -> bool:
        """Проверить код валюты"""
        return code.upper() in CurrencyValidator.SUPPORTED_CURRENCIES

    @staticmethod
    def validate_amount(amount: float) -> bool:
        """Проверить сумму"""
        return isinstance(amount, (int, float)) and amount > 0
