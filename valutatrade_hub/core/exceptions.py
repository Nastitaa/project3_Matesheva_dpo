# valutatrade_hub/core/exceptions.py


class ValutaTradeError(Exception):
    """Базовый класс для всех ошибок ValutaTrade"""
    
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
    
    def __str__(self) -> str:
        return self.message


class InsufficientFundsError(ValutaTradeError):
    """Ошибка недостаточных средств"""
    
    def __init__(self, currency_code: str, available: float, required: float):
        message = (
            f"Недостаточно средств: доступно {available:.8f} {currency_code}, "
            f"требуется {required:.8f} {currency_code}"
        )
        super().__init__(message)
        self.currency_code = currency_code
        self.available = available
        self.required = required


class CurrencyNotFoundError(ValutaTradeError):
    """Ошибка неизвестной валюты"""
    
    def __init__(self, currency_code: str):
        message = f"Неизвестная валюта '{currency_code}'"
        super().__init__(message)
        self.currency_code = currency_code


class ApiRequestError(ValutaTradeError):
    """Ошибка при обращении к внешнему API"""
    
    def __init__(self, reason: str, status_code: int = None):
        message = f"Ошибка при обращении к внешнему API: {reason}"
        if status_code:
            message += f" (код: {status_code})"
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


class AuthenticationError(ValutaTradeError):
    """Ошибка аутентификации"""
    
    def __init__(self, message: str = "Ошибка аутентификации"):
        super().__init__(message)


class UserAlreadyExistsError(ValutaTradeError):
    """Ошибка: пользователь уже существует"""
    
    def __init__(self, username: str):
        message = f"Пользователь '{username}' уже существует"
        super().__init__(message)
        self.username = username


class InvalidAmountError(ValutaTradeError):
    """Ошибка некорректной суммы"""
    
    def __init__(self, amount: float):
        message = f"Некорректная сумма: {amount}. Сумма должна быть положительным числом"
        super().__init__(message)
        self.amount = amount


class InvalidCurrencyCodeError(ValutaTradeError):
    """Ошибка некорректного кода валюты"""
    
    def __init__(self, code: str):
        message = f"Некорректный код валюты: {code}"
        super().__init__(message)
        self.code = code


class CurrencyRegistrationError(ValutaTradeError):
    """Ошибка регистрации валюты"""
    
    def __init__(self, message: str):
        super().__init__(message)


class DatabaseError(ValutaTradeError):
    """Ошибка базы данных"""
    
    def __init__(self, message: str):
        super().__init__(f"Ошибка базы данных: {message}")


class ConfigError(ValutaTradeError):
    """Ошибка конфигурации"""
    
    def __init__(self, message: str):
        super().__init__(f"Ошибка конфигурации: {message}")