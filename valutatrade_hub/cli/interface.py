# valutatrade_hub/cli/interface.py
import cmd
import sys
import argparse
import shlex
from typing import Optional, List
from prettytable import PrettyTable
from decimal import Decimal
import logging

from ..core.usecases import (
    UserManager,
    PortfolioManager,
    ExchangeRateService,
    TransactionManager,
    TradeService,
    TradeResult
)
from ..core.models import User
from ..core.currencies import CurrencyRegistry
from ..core.exceptions import (
    ValutaTradeError,
    InsufficientFundsError,
    CurrencyNotFoundError,
    ApiRequestError,
    AuthenticationError,
    UserAlreadyExistsError,
    InvalidAmountError
)
from ..core.utils import CLIFormatter, CurrencyValidator
from ..infra.settings import SettingsLoader
from ..decorators import log_action, confirm_action
from ..logging_config import setup_logging, get_logger


class ValutaTradeCLI(cmd.Cmd):
    """Консольный интерфейс для торговли валютами"""
    
    intro = """
    ============================================
    ValutaTrade Hub - Торговая платформа
    ============================================
    
    Для списка команд введите: help
    Для помощи по команде введите: help <команда>
    """
    prompt = "(valutatrade) "
    
    def __init__(self):
        super().__init__()
        
        # Настройка логирования
        setup_logging()
        self.logger = get_logger(__name__)
        
        # Инициализация сервисов
        self.settings = SettingsLoader()
        self.user_manager = UserManager()
        self.portfolio_manager = PortfolioManager()
        self.exchange_service = ExchangeRateService()
        self.transaction_manager = TransactionManager()
        self.trade_service = TradeService()
        
        self.current_user: Optional[User] = None
        
        self.logger.info("CLI инициализирован", extra={
            'action': 'CLI_INIT',
            'result': 'OK'
        })
    
    # ========== Вспомогательные методы ==========
    
    def require_login(self) -> bool:
        """Требовать вход в систему"""
        if not self.current_user:
            print("❌ Ошибка: Сначала выполните login")
            self.logger.warning("Попытка выполнить команду без авторизации")
            return False
        return True
    
    def parse_args(self, arg_string: str) -> List[str]:
        """Разобрать аргументы командной строки"""
        try:
            return shlex.split(arg_string)
        except ValueError as e:
            print(f"❌ Ошибка разбора аргументов: {e}")
            return []
    
    def handle_error(self, error: Exception, context: str = "") -> None:
        """Обработка ошибок"""
        if isinstance(error, ValutaTradeError):
            # Пользовательские ошибки
            print(f"❌ {error}")
            
            # Дополнительные действия для разных типов ошибок
            if isinstance(error, CurrencyNotFoundError):
                print("\n💡 Подсказка:")
                print("   - Проверьте правильность кода валюты")
                print("   - Используйте команду 'list-currencies' для списка доступных валют")
                print("   - Код валюты должен быть в верхнем регистре (например, USD, BTC)")
            
            elif isinstance(error, ApiRequestError):
                print("\n💡 Подсказка:")
                print("   - Проверьте подключение к интернету")
                print("   - Повторите попытку позже")
                print("   - Используйте команду 'get-rate' для проверки доступности курсов")
            
            elif isinstance(error, InsufficientFundsError):
                print("\n💡 Подсказка:")
                print("   - Проверьте баланс с помощью команды 'show-portfolio'")
                print("   - Пополните баланс командой 'deposit'")
                print("   - Уменьшите сумму операции")
            
            elif isinstance(error, AuthenticationError):
                print("\n💡 Подсказка:")
                print("   - Проверьте правильность имени пользователя и пароля")
                print("   - Если забыли пароль, обратитесь к администратору")
            
            elif isinstance(error, UserAlreadyExistsError):
                print("\n💡 Подсказка:")
                print("   - Выберите другое имя пользователя")
                print("   - Или выполните вход с существующим именем")
        
        else:
            # Системные ошибки
            print(f"❌ Системная ошибка: {error}")
            
            if self.settings.get('app.debug', False):
                import traceback
                traceback.print_exc()
        
        # Логирование ошибки
        self.logger.error(f"Ошибка в команде {context}: {error}", extra={
            'action': context,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'result': 'ERROR'
        })
    
    # ========== Команда: register ==========
    
    @log_action(level=20, include_args=True, include_result=True)
    def do_register(self, arg):
        """
        Регистрация нового пользователя
        Использование: register --username <имя> --password <пароль> [--email <email>]
        """
        parser = argparse.ArgumentParser(prog='register')
        parser.add_argument('--username', required=True, help='Имя пользователя')
        parser.add_argument('--password', required=True, help='Пароль (мин. 4 символа)')
        parser.add_argument('--email', help='Email адрес (опционально)')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Регистрация пользователя
            user = self.user_manager.register_user(
                username=args.username,
                password=args.password,
                email=args.email
            )
            
            print(f"\n✅ Пользователь '{args.username}' успешно зарегистрирован!")
            print(f"   ID пользователя: {user.user_id}")
            print(f"   Дата регистрации: {user.registration_date.strftime('%Y-%m-%d %H:%M')}")
            
            if args.email:
                print(f"   Email: {args.email}")
            
            print(f"\n📋 Теперь вы можете войти в систему:")
            print(f"   login --username {args.username} --password {args.password}")
            
        except ValutaTradeError as e:
            self.handle_error(e, "REGISTER")
        except Exception as e:
            self.handle_error(e, "REGISTER")
    
    # ========== Команда: login ==========
    
    @log_action(level=20, include_args=True, include_result=True)
    def do_login(self, arg):
        """
        Вход в систему
        Использование: login --username <имя> --password <пароль>
        """
        parser = argparse.ArgumentParser(prog='login')
        parser.add_argument('--username', required=True, help='Имя пользователя')
        parser.add_argument('--password', required=True, help='Пароль')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            user = self.user_manager.authenticate_user(args.username, args.password)
            
            if user:
                self.current_user = user
                self.prompt = f"({args.username}) "
                
                print(f"\n✅ Вы успешно вошли как '{args.username}'!")
                print(f"   Добро пожаловать в ValutaTrade Hub!")
                
                # Показываем баланс при входе
                self._show_welcome_balance()
                
                self.logger.info(f"Пользователь {args.username} вошел в систему", extra={
                    'action': 'LOGIN',
                    'username': args.username,
                    'user_id': user.user_id,
                    'result': 'OK'
                })
            else:
                print("❌ Неверное имя пользователя или пароль")
                
        except ValutaTradeError as e:
            self.handle_error(e, "LOGIN")
        except Exception as e:
            self.handle_error(e, "LOGIN")
    
    def _show_welcome_balance(self) -> None:
        """Показать баланс при входе"""
        try:
            portfolio = self.portfolio_manager.get_user_portfolio(self.current_user.user_id)
            
            if portfolio.wallets:
                print(f"\n💰 Ваш текущий баланс:")
                for currency_code, wallet in portfolio.wallets.items():
                    if wallet.balance > Decimal('0'):
                        print(f"   - {wallet.get_balance_info()}")
        except Exception as e:
            self.logger.warning(f"Не удалось показать баланс при входе: {e}")
    
    # ========== Команда: logout ==========
    
    def do_logout(self, _):
        """Выйти из системы"""
        if self.current_user:
            username = self.current_user.username
            self.current_user = None
            self.prompt = "(valutatrade) "
            
            print(f"\n👋 До свидания, {username}!")
            print("   Вы вышли из системы.")
            
            self.logger.info(f"Пользователь {username} вышел из системы", extra={
                'action': 'LOGOUT',
                'username': username,
                'result': 'OK'
            })
        else:
            print("ℹ️  Вы не вошли в систему")
    
    # ========== Команда: show-portfolio ==========
    
    @log_action(include_args=True, include_result=True)
    def do_show_portfolio(self, arg):
        """
        Показать портфель пользователя
        Использование: show-portfolio [--base <валюта>] [--detailed]
        """
        if not self.require_login():
            return
        
        parser = argparse.ArgumentParser(prog='show-portfolio')
        parser.add_argument('--base', default='USD', help='Базовая валюта для конвертации')
        parser.add_argument('--detailed', action='store_true', help='Подробная информация')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Получение стоимости портфеля
            portfolio_value = self.trade_service.get_portfolio_value(
                self.current_user.user_id,
                args.base
            )
            
            total_value = portfolio_value['total_value']
            base_currency = portfolio_value['base_currency']
            currencies = portfolio_value['currencies']
            
            if not currencies:
                print(f"\n📭 Портфель пользователя '{self.current_user.username}' пуст.")
                print(f"   Используйте команду 'deposit' для пополнения баланса.")
                return
            
            # Создание таблицы
            table = PrettyTable()
            
            if args.detailed:
                table.field_names = ["Валюта", "Тип", "Баланс", f"В {base_currency}", f"Курс {base_currency}", "Информация"]
                table.align = {"Валюта": "l", "Тип": "c", "Баланс": "r", f"В {base_currency}": "r", f"Курс {base_currency}": "r", "Информация": "l"}
            else:
                table.field_names = ["Валюта", "Баланс", f"В {base_currency}", f"Курс {base_currency}"]
                table.align = {"Валюта": "l", "Баланс": "r", f"В {base_currency}": "r", f"Курс {base_currency}": "r"}
            
            for currency_code, data in currencies.items():
                balance = data['balance']
                value_in_base = data['value_in_base']
                
                # Получаем курс
                try:
                    rate = self.exchange_service.get_rate(currency_code, base_currency)
                    rate_str = f"{rate:.6f}" if rate < 1 else f"{rate:.2f}"
                except:
                    rate_str = "N/A"
                
                # Форматируем значения
                balance_str = CLIFormatter.format_currency(balance, currency_code)
                value_str = CLIFormatter.format_currency(value_in_base, base_currency)
                
                if args.detailed:
                    currency_info = data['currency_info']
                    # Определяем тип валюты
                    currency_type = "FIAT" if "FIAT" in currency_info else "CRYPTO"
                    
                    table.add_row([
                        currency_code,
                        currency_type,
                        balance_str,
                        value_str,
                        rate_str,
                        currency_info
                    ])
                else:
                    table.add_row([
                        currency_code,
                        balance_str,
                        value_str,
                        rate_str
                    ])
            
            print(f"\n📊 Портфель пользователя '{self.current_user.username}' (база: {base_currency}):")
            print(table)
            print(f"\n💰 ИТОГО: {CLIFormatter.format_currency(total_value, base_currency)}")
            
            # Показываем рекомендации
            self._show_portfolio_recommendations(currencies, total_value)
            
        except ValutaTradeError as e:
            self.handle_error(e, "SHOW_PORTFOLIO")
        except Exception as e:
            self.handle_error(e, "SHOW_PORTFOLIO")
    
    def _show_portfolio_recommendations(self, currencies: dict, total_value: Decimal) -> None:
        """Показать рекомендации по портфелю"""
        if len(currencies) == 1:
            print(f"\n💡 Рекомендация: Добавьте другие валюты для диверсификации портфеля.")
        elif total_value < Decimal('100'):
            print(f"\n💡 Рекомендация: Пополните баланс для более активной торговли.")
    
    # ========== Команда: buy ==========
    
    @confirm_action("Вы уверены, что хотите совершить покупку?")
    @log_action(level=20, include_args=True, include_result=True, verbose=True)
    def do_buy(self, arg):
        """
        Купить валюту
        Использование: buy --currency <код> --amount <сумма> [--base <валюта>]
        """
        if not self.require_login():
            return
        
        parser = argparse.ArgumentParser(prog='buy')
        parser.add_argument('--currency', required=True, help='Код покупаемой валюты')
        parser.add_argument('--amount', required=True, help='Количество покупаемой валюты')
        parser.add_argument('--base', default='USD', help='Валюта для оплаты')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Валидация валюты
            if not CurrencyValidator.validate_currency_code(args.currency):
                print(f"❌ Некорректный код валюты: {args.currency}")
                return
            
            # Валидация суммы
            try:
                amount = CurrencyValidator.validate_amount(args.amount)
            except ValueError as e:
                print(f"❌ {e}")
                return
            
            # Получаем информацию о валюте
            currency = CurrencyRegistry.get_currency(args.currency)
            
            # Показываем детали операции
            rate = self.exchange_service.get_rate(args.base, args.currency)
            
            print(f"\n📝 Детали операции покупки:")
            print(f"   Покупаемая валюта: {currency.get_display_info()}")
            print(f"   Количество: {CLIFormatter.format_currency(amount, args.currency)}")
            print(f"   Валюта оплаты: {args.base}")
            print(f"   Текущий курс: {CLIFormatter.format_rate(rate, args.base, args.currency)}")
            print(f"   Ориентировочная стоимость: {CLIFormatter.format_currency(amount * rate, args.base)}")
            
            # Выполняем покупку
            result = self.trade_service.buy_currency(
                user_id=self.current_user.user_id,
                currency=args.currency,
                amount=amount,
                base_currency=args.base
            )
            
            if result.success:
                print(f"\n{result.message}")
                
                # Показываем изменения в портфеле
                print(f"\n📈 Изменения в портфеле:")
                for currency_code, old_balance in result.old_balances.items():
                    new_balance = result.new_balances[currency_code]
                    if old_balance != new_balance:
                        print(f"   - {currency_code}: {CLIFormatter.format_currency(old_balance, currency_code)} "
                              f"→ {CLIFormatter.format_currency(new_balance, currency_code)}")
                
        except ValutaTradeError as e:
            self.handle_error(e, "BUY")
        except Exception as e:
            self.handle_error(e, "BUY")
    
    # ========== Команда: sell ==========
    
    @confirm_action("Вы уверены, что хотите совершить продажу?")
    @log_action(level=20, include_args=True, include_result=True, verbose=True)
    def do_sell(self, arg):
        """
        Продать валюту
        Использование: sell --currency <код> --amount <сумма> [--target <валюта>]
        """
        if not self.require_login():
            return
        
        parser = argparse.ArgumentParser(prog='sell')
        parser.add_argument('--currency', required=True, help='Код продаваемой валюты')
        parser.add_argument('--amount', required=True, help='Количество продаваемой валюты')
        parser.add_argument('--target', default='USD', help='Валюта для получения')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Валидация валюты
            if not CurrencyValidator.validate_currency_code(args.currency):
                print(f"❌ Некорректный код валюты: {args.currency}")
                return
            
            # Валидация суммы
            try:
                amount = CurrencyValidator.validate_amount(args.amount)
            except ValueError as e:
                print(f"❌ {e}")
                return
            
            # Получаем информацию о валюте
            currency = CurrencyRegistry.get_currency(args.currency)
            
            # Показываем детали операции
            rate = self.exchange_service.get_rate(args.currency, args.target)
            
            print(f"\n📝 Детали операции продажи:")
            print(f"   Продаваемая валюта: {currency.get_display_info()}")
            print(f"   Количество: {CLIFormatter.format_currency(amount, args.currency)}")
            print(f"   Валюта получения: {args.target}")
            print(f"   Текущий курс: {CLIFormatter.format_rate(rate, args.currency, args.target)}")
            print(f"   Ориентировочная выручка: {CLIFormatter.format_currency(amount * rate, args.target)}")
            
            # Выполняем продажу
            result = self.trade_service.sell_currency(
                user_id=self.current_user.user_id,
                currency=args.currency,
                amount=amount,
                target_currency=args.target
            )
            
            if result.success:
                print(f"\n{result.message}")
                
                # Показываем изменения в портфеле
                print(f"\n📉 Изменения в портфеле:")
                for currency_code, old_balance in result.old_balances.items():
                    new_balance = result.new_balances[currency_code]
                    if old_balance != new_balance:
                        print(f"   - {currency_code}: {CLIFormatter.format_currency(old_balance, currency_code)} "
                              f"→ {CLIFormatter.format_currency(new_balance, currency_code)}")
                
        except ValutaTradeError as e:
            self.handle_error(e, "SELL")
        except Exception as e:
            self.handle_error(e, "SELL")
    
    # ========== Команда: get-rate ==========
    
    @log_action(include_args=True, include_result=True)
    def do_get_rate(self, arg):
        """
        Получить текущий курс валюты
        Использование: get-rate --from <валюта> --to <валюта>
        """
        parser = argparse.ArgumentParser(prog='get-rate')
        parser.add_argument('--from', dest='from_currency', required=True, help='Исходная валюта')
        parser.add_argument('--to', dest='to_currency', required=True, help='Целевая валюта')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Валидация валют
            if not CurrencyValidator.validate_currency_code(args.from_currency):
                print(f"❌ Некорректный код валюты: {args.from_currency}")
                return
            
            if not CurrencyValidator.validate_currency_code(args.to_currency):
                print(f"❌ Некорректный код валюты: {args.to_currency}")
                return
            
            # Получаем информацию о валютах
            from_currency = CurrencyRegistry.get_currency(args.from_currency)
            to_currency = CurrencyRegistry.get_currency(args.to_currency)
            
            # Получаем курс
            rate = self.exchange_service.get_rate(args.from_currency, args.to_currency)
            
            # Получаем информацию о времени обновления
            rates_data = self.exchange_service._rates_cache.get("rates", {})
            pair_key = f"{args.from_currency.upper()}_{args.to_currency.upper()}"
            
            if pair_key in rates_data:
                rate_info = rates_data[pair_key]
                updated_at = rate_info.get("updated_at", "")
                source = rate_info.get("source", "unknown")
            else:
                updated_at = ""
                source = "calculated"
            
            # Форматируем вывод
            print(f"\n💱 Курс валют:")
            print(f"   От: {from_currency.get_display_info()}")
            print(f"   К: {to_currency.get_display_info()}")
            print(f"   Курс: {CLIFormatter.format_rate(rate, args.from_currency, args.to_currency)}")
            
            if updated_at:
                try:
                    from datetime import datetime
                    updated_time = datetime.fromisoformat(updated_at)
                    print(f"   Обновлено: {updated_time.strftime('%Y-%m-%d %H:%M:%S')}")
                except:
                    pass
            
            print(f"   Источник: {source}")
            
            # Показываем обратный курс
            if rate != Decimal('1.0'):
                reverse_rate = Decimal('1.0') / rate
                print(f"   Обратный курс: {CLIFormatter.format_rate(reverse_rate, args.to_currency, args.from_currency)}")
            
        except CurrencyNotFoundError as e:
            self.handle_error(e, "GET_RATE")
        except ApiRequestError as e:
            self.handle_error(e, "GET_RATE")
        except Exception as e:
            self.handle_error(e, "GET_RATE")
    
    # ========== Команда: deposit ==========
    
    @log_action(include_args=True, include_result=True)
    def do_deposit(self, arg):
        """
        Пополнить баланс
        Использование: deposit --currency <код> --amount <сумма>
        """
        if not self.require_login():
            return
        
        parser = argparse.ArgumentParser(prog='deposit')
        parser.add_argument('--currency', default='USD', help='Валюта пополнения')
        parser.add_argument('--amount', required=True, help='Сумма пополнения')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            # Валидация валюты
            if not CurrencyValidator.validate_currency_code(args.currency):
                print(f"❌ Некорректный код валюты: {args.currency}")
                return
            
            # Валидация суммы
            try:
                amount = CurrencyValidator.validate_amount(args.amount)
            except ValueError as e:
                print(f"❌ {e}")
                return
            
            # Получаем или создаем кошелек
            wallet = self.portfolio_manager.ensure_wallet_exists(
                self.current_user.user_id,
                args.currency
            )
            
            old_balance = wallet.balance
            wallet.deposit(amount)
            
            # Сохраняем портфель
            portfolio = self.portfolio_manager.get_user_portfolio(self.current_user.user_id)
            self.portfolio_manager.save_portfolio(portfolio)
            
            # Создаем транзакцию
            self.transaction_manager.create_transaction(
                user_id=self.current_user.user_id,
                type="deposit",
                from_currency=None,
                to_currency=args.currency,
                amount=amount,
                rate=None,
                description=f"Пополнение баланса"
            )
            
            print(f"\n✅ Баланс успешно пополнен!")
            print(f"   Пополнено: {CLIFormatter.format_currency(amount, args.currency)}")
            print(f"   Было: {CLIFormatter.format_currency(old_balance, args.currency)}")
            print(f"   Стало: {CLIFormatter.format_currency(wallet.balance, args.currency)}")
            
        except ValutaTradeError as e:
            self.handle_error(e, "DEPOSIT")
        except Exception as e:
            self.handle_error(e, "DEPOSIT")
    
    # ========== Команда: profile ==========
    
    def do_profile(self, _):
        """Показать профиль пользователя"""
        if not self.require_login():
            return
        
        try:
            print(f"\n👤 Профиль пользователя:")
            print(f"   {self.current_user.get_user_info()}")
            
            # Статистика транзакций
            summary = self.transaction_manager.get_transaction_summary(
                self.current_user.user_id
            )
            
            if summary["total_transactions"] > 0:
                print(f"\n📊 Статистика транзакций:")
                print(f"   Всего операций: {summary['total_transactions']}")
                print(f"   Покупок: {CLIFormatter.format_currency(summary['total_buy'], '')}")
                print(f"   Продаж: {CLIFormatter.format_currency(summary['total_sell'], '')}")
                print(f"   Пополнений: {CLIFormatter.format_currency(summary['total_deposit'], '')}")
                print(f"   Выводов: {CLIFormatter.format_currency(summary['total_withdraw'], '')}")
            
        except Exception as e:
            self.handle_error(e, "PROFILE")
    
    # ========== Новые команды ==========
    
    def do_list_currencies(self, _):
        """Показать список поддерживаемых валют"""
        try:
            supported = CurrencyRegistry.get_supported_currencies()
            
            if not supported:
                print("❌ Список валют пуст")
                return
            
            table = PrettyTable()
            table.field_names = ["Код", "Тип", "Название"]
            table.align = {"Код": "l", "Тип": "c", "Название": "l"}
            
            for code, info in sorted(supported.items()):
                if "FIAT" in info:
                    currency_type = "FIAT"
                    name = info.replace("FIAT - ", "")
                else:
                    currency_type = "CRYPTO"
                    name = info.replace("CRYPTO - ", "")
                
                table.add_row([code, currency_type, name])
            
            print(f"\n💱 Поддерживаемые валюты ({len(supported)}):")
            print(table)
            
        except Exception as e:
            self.handle_error(e, "LIST_CURRENCIES")
    
    def do_transactions(self, arg):
        """
        Показать историю транзакций
        Использование: transactions [--limit <число>] [--offset <число>]
        """
        if not self.require_login():
            return
        
        parser = argparse.ArgumentParser(prog='transactions')
        parser.add_argument('--limit', type=int, default=10, help='Количество транзакций')
        parser.add_argument('--offset', type=int, default=0, help='Смещение')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            transactions = self.transaction_manager.get_user_transactions(
                self.current_user.user_id,
                limit=args.limit,
                offset=args.offset
            )
            
            if not transactions:
                print(f"\n📭 У вас нет транзакций.")
                return
            
            table = PrettyTable()
            table.field_names = ["ID", "Дата", "Тип", "Сумма", "От", "К", "Курс", "Комиссия"]
            table.align = {"ID": "r", "Дата": "l", "Тип": "c", "Сумма": "r", "От": "l", "К": "l", "Курс": "r", "Комиссия": "r"}
            
            for t in transactions:
                # Форматируем дату
                date_str = t.timestamp.strftime('%Y-%m-%d %H:%M')
                
                # Форматируем сумму
                if t.type in ["buy", "deposit"]:
                    amount_str = CLIFormatter.format_currency(t.amount, t.to_currency or "")
                else:
                    amount_str = CLIFormatter.format_currency(t.amount, t.from_currency or "")
                
                # Форматируем курс
                rate_str = f"{t.rate:.6f}" if t.rate else "N/A"
                
                # Форматируем комиссию
                fee_str = CLIFormatter.format_currency(t.fee, "USD") if t.fee else "N/A"
                
                table.add_row([
                    t.transaction_id,
                    date_str,
                    t.type.upper(),
                    amount_str,
                    t.from_currency or "",
                    t.to_currency or "",
                    rate_str,
                    fee_str
                ])
            
            print(f"\n📋 История транзакций (показано {len(transactions)} из {args.limit + args.offset}):")
            print(table)
            
        except Exception as e:
            self.handle_error(e, "TRANSACTIONS")
    
    def do_settings(self, arg):
        """
        Показать или изменить настройки
        Использование: settings [--key <ключ> --value <значение>]
        """
        parser = argparse.ArgumentParser(prog='settings')
        parser.add_argument('--key', help='Ключ настройки')
        parser.add_argument('--value', help='Новое значение')
        
        try:
            args = parser.parse_args(self.parse_args(arg))
        except SystemExit:
            return
        
        try:
            if args.key and args.value:
                # Изменение настройки
                self.settings.set(args.key, args.value)
                self.settings.save()
                print(f"✅ Настройка '{args.key}' обновлена на '{args.value}'")
            elif args.key:
                # Показать конкретную настройку
                value = self.settings.get(args.key)
                if value is None:
                    print(f"❌ Настройка '{args.key}' не найдена")
                else:
                    print(f"📋 {args.key}: {value}")
            else:
                # Показать все настройки
                config = self.settings.get_all()
                
                table = PrettyTable()
                table.field_names = ["Ключ", "Значение"]
                table.align = {"Ключ": "l", "Значение": "l"}
                
                def add_settings(data: dict, prefix: str = ""):
                    for key, value in data.items():
                        full_key = f"{prefix}.{key}" if prefix else key
                        
                        if isinstance(value, dict):
                            add_settings(value, full_key)
                        else:
                            # Обрезаем длинные значения
                            value_str = str(value)
                            if len(value_str) > 50:
                                value_str = value_str[:47] + "..."
                            table.add_row([full_key, value_str])
                
                add_settings(config)
                
                print(f"\n⚙️  Настройки приложения:")
                print(table)
                
        except Exception as e:
            self.handle_error(e, "SETTINGS")
    
    # ========== Системные команды ==========
    
    def do_clear(self, _):
        """Очистить экран"""
        print("\033[H\033[J", end="")
    
    def do_status(self, _):
        """Показать статус системы"""
        try:
            print(f"\n📊 Статус системы:")
            
            # Статус пользователя
            if self.current_user:
                print(f"   Пользователь: {self.current_user.username} (ID: {self.current_user.user_id})")
            else:
                print(f"   Пользователь: не авторизован")
            
            # Статистика базы данных
            db = DatabaseManager()
            files = ['users.json', 'portfolios.json', 'rates.json', 'transactions.json']
            
            for filename in files:
                try:
                    data = db.read_data(filename, use_cache=False)
                    if isinstance(data, list):
                        count = len(data)
                    elif isinstance(data, dict):
                        count = len(data)
                    else:
                        count = 0
                    print(f"   {filename}: {count} записей")
                except:
                    print(f"   {filename}: ошибка чтения")
            
            # Статус курсов
            rates = self.exchange_service._rates_cache
            if rates and 'metadata' in rates:
                last_refresh = rates['metadata'].get('last_refresh', 'неизвестно')
                print(f"   Курсы обновлены: {last_refresh}")
            
            print(f"   Режим отладки: {'включен' if self.settings.get('app.debug') else 'выключен'}")
            
        except Exception as e:
            self.handle_error(e, "STATUS")
    
    def do_help(self, arg):
        """Показать справку по командам"""
        commands = {
            'register': 'Зарегистрировать нового пользователя',
            'login': 'Войти в систему',
            'logout': 'Выйти из системы',
            'show-portfolio': 'Показать портфель',
            'buy': 'Купить валюту',
            'sell': 'Продать валюту',
            'get-rate': 'Получить курс валюты',
            'deposit': 'Пополнить баланс',
            'profile': 'Показать профиль',
            'list-currencies': 'Список поддерживаемых валют',
            'transactions': 'История транзакций',
            'settings': 'Настройки приложения',
            'status': 'Статус системы',
            'clear': 'Очистить экран',
            'exit': 'Выйти из приложения'
        }
        
        if arg:
            if arg in commands:
                method = getattr(self, f'do_{arg}', None)
                if method and method.__doc__:
                    print(f"\n{arg.upper()}:")
                    print(method.__doc__)
                else:
                    print(f"Команда '{arg}': {commands.get(arg, 'Описание недоступно')}")
            else:
                print(f"❌ Неизвестная команда: {arg}")
        else:
            print("\n📖 Доступные команды:")
            table = PrettyTable()
            table.field_names = ["Команда", "Описание"]
            table.align = {"Команда": "l", "Описание": "l"}
            
            for cmd_name, description in sorted(commands.items()):
                table.add_row([cmd_name, description])
            
            print(table)
            print("\n💡 Для подробной справки по команде введите: help <команда>")
    
    def do_exit(self, _):
        """Выйти из приложения"""
        if self.current_user:
            self.do_logout(_)
        
        print("\n👋 До свидания! Спасибо за использование ValutaTrade Hub!")
        self.logger.info("Приложение завершено", extra={'action': 'EXIT', 'result': 'OK'})
        return True
    
    def do_quit(self, _):
        """Выйти из приложения"""
        return self.do_exit(_)
    
    def default(self, line):
        print(f"❌ Неизвестная команда: {line}")
        print("💡 Введите help для списка команд")
    
    def emptyline(self):
        pass


def main():
    """Точка входа в CLI"""
    try:
        cli = ValutaTradeCLI()
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\n\n👋 Приложение завершено пользователем")
        sys.exit(0)
    except Exception as e:
        logger = get_logger(__name__)
        logger.critical(f"Критическая ошибка в CLI: {e}", exc_info=True)
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)

# ========== Команды парсинга ==========

def do_update_rates(self, arg):
    """
    Обновить курсы валют
    Использование: update-rates [--source <источник>] [--force]
    """
    parser = argparse.ArgumentParser(prog='update-rates')
    parser.add_argument('--source', 
                       choices=['coingecko', 'exchangerate', 'all'],
                       default='all',
                       help='Источник данных (coingecko, exchangerate, all)')
    parser.add_argument('--force', 
                       action='store_true',
                       help='Принудительное обновление даже если курсы актуальны')
    
    try:
        args = parser.parse_args(self.parse_args(arg))
    except SystemExit:
        return
    
    try:
        # Инициализируем парсер
        from ..parser_service.updater import RatesUpdater
        from ..parser_service.config import ParserConfig
        
        config = ParserConfig()
        updater = RatesUpdater(config)
        
        print(f"\n🔄 Начало обновления курсов...")
        print(f"   Источник: {args.source}")
        print(f"   Режим: {'принудительный' if args.force else 'только устаревшие'}")
        
        # Запускаем обновление
        result = updater.run_update(
            source_filter=args.source if args.source != 'all' else None,
            force_update=args.force
        )
        
        if result.success:
            print(f"\n✅ Обновление успешно завершено!")
            print(f"   Получено курсов: {result.total_rates}")
            print(f"   Обновлено пар: {len(result.updated_pairs)}")
            print(f"   Затрачено времени: {result.duration_ms:.2f} мс")
            
            if result.updated_pairs:
                print(f"\n📈 Обновленные пары:")
                for pair in result.updated_pairs[:10]:  # Показываем первые 10
                    print(f"   - {pair}")
                if len(result.updated_pairs) > 10:
                    print(f"   ... и еще {len(result.updated_pairs) - 10} пар")
            
            if result.failed_sources:
                print(f"\n⚠️  Ошибки в источниках: {', '.join(result.failed_sources)}")
        
        else:
            print(f"\n❌ Обновление завершено с ошибками")
            print(f"   Ошибки: {', '.join(result.errors)}")
            
            if result.failed_sources:
                print(f"   Неудачные источники: {', '.join(result.failed_sources)}")
        
        # Показываем статус
        status = updater.get_update_status()
        if status.get('last_refresh'):
            from datetime import datetime
            last_refresh = datetime.fromisoformat(status['last_refresh'].replace('Z', '+00:00'))
            print(f"\n📊 Статус кэша:")
            print(f"   Последнее обновление: {last_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Актуальных курсов: {status['cache_status'].get('fresh', 0)}")
            print(f"   Устаревших курсов: {status['cache_status'].get('stale', 0)}")
        
    except Exception as e:
        self.handle_error(e, "UPDATE_RATES")

def do_show_rates(self, arg):
    """
    Показать курсы валют из кэша
    Использование: show-rates [--currency <валюта>] [--top <N>] [--base <валюта>] [--history]
    """
    parser = argparse.ArgumentParser(prog='show-rates')
    parser.add_argument('--currency', help='Показать курс только для указанной валюты')
    parser.add_argument('--top', type=int, help='Показать N самых дорогих криптовалют')
    parser.add_argument('--base', default='USD', help='Базовая валюта для отображения')
    parser.add_argument('--history', action='store_true', help='Показать исторические данные')
    parser.add_argument('--limit', type=int, default=10, help='Лимит записей для истории')
    
    try:
        args = parser.parse_args(self.parse_args(arg))
    except SystemExit:
        return
    
    try:
        from ..parser_service.storage import RatesStorage
        from ..parser_service.config import ParserConfig
        from prettytable import PrettyTable
        
        config = ParserConfig()
        storage = RatesStorage(config)
        
        if args.history:
            # Показать исторические данные
            history = storage.load_history(
                limit=args.limit,
                currency_pair=args.currency
            )
            
            if not history:
                print(f"\n📭 Исторические данные не найдены")
                if args.currency:
                    print(f"   Для валюты: {args.currency}")
                return
            
            table = PrettyTable()
            table.field_names = ["Дата", "Пара", "Курс", "Источник"]
            table.align = {"Дата": "l", "Пара": "c", "Курс": "r", "Источник": "l"}
            
            for record in history:
                timestamp = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
                date_str = timestamp.strftime('%Y-%m-%d %H:%M')
                pair = f"{record['from_currency']}/{record['to_currency']}"
                rate = record['rate']
                source = record['source']
                
                table.add_row([date_str, pair, f"{rate:.6f}", source])
            
            print(f"\n📊 Исторические данные курсов:")
            if args.currency:
                print(f"   Для пары: {args.currency}")
            print(f"   Показано записей: {len(history)}")
            print(table)
            
        else:
            # Показать текущие курсы
            rates_data = storage.load_current_rates()
            pairs = rates_data.get('pairs', {})
            
            if not pairs:
                print(f"\n📭 Кэш курсов пуст")
                print(f"   Используйте команду 'update-rates' для загрузки данных")
                return
            
            # Фильтрация по валюте
            filtered_pairs = {}
            if args.currency:
                currency = args.currency.upper()
                for pair_key, data in pairs.items():
                    if currency in pair_key:
                        filtered_pairs[pair_key] = data
            else:
                filtered_pairs = pairs
            
            if not filtered_pairs:
                print(f"\n❌ Курсы для валюты '{args.currency}' не найдены")
                return
            
            # Сортировка
            sorted_pairs = sorted(
                filtered_pairs.items(),
                key=lambda x: x[1]['rate'],
                reverse=True
            )
            
            # Применяем топ-N фильтр
            if args.top:
                sorted_pairs = sorted_pairs[:args.top]
            
            # Создаем таблицу
            table = PrettyTable()
            table.field_names = ["Пара", "Курс", "Обновлено", "Источник", "Статус"]
            table.align = {"Пара": "l", "Курс": "r", "Обновлено": "l", "Источник": "l", "Статус": "c"}
            
            for pair_key, data in sorted_pairs:
                rate = data['rate']
                updated_at = datetime.fromisoformat(data['updated_at'].replace('Z', '+00:00'))
                updated_str = updated_at.strftime('%H:%M')
                source = data['source']
                
                # Проверяем актуальность
                is_fresh = storage.is_rate_fresh(pair_key)
                status = "🟢" if is_fresh else "🟡"
                
                table.add_row([pair_key, f"{rate:.6f}", updated_str, source, status])
            
            metadata = rates_data.get('metadata', {})
            last_refresh = metadata.get('last_refresh', 'неизвестно')
            
            print(f"\n💱 Текущие курсы валют:")
            print(f"   Всего пар: {len(pairs)}")
            print(f"   Показано: {len(sorted_pairs)}")
            print(f"   Последнее обновление: {last_refresh}")
            print(table)
            
            # Статус кэша
            fresh_count = sum(1 for data in pairs.values() 
                            if storage.is_rate_fresh(list(pairs.keys())[0]))
            
            print(f"\n📊 Статус кэша:")
            print(f"   Актуальных курсов: {fresh_count}")
            print(f"   Устаревших курсов: {len(pairs) - fresh_count}")
            print(f"   TTL: {config.CACHE_TTL_SECONDS} секунд")
            
            if args.top:
                print(f"\n💎 Топ-{args.top} самых дорогих криптовалют:")
                crypto_pairs = [(k, v) for k, v in sorted_pairs 
                              if any(crypto in k for crypto in config.CRYPTO_CURRENCIES)]
                for i, (pair_key, data) in enumerate(crypto_pairs[:args.top], 1):
                    currency = pair_key.split('_')[0]
                    rate = data['rate']
                    print(f"   {i}. {currency}: ${rate:,.2f}")
    
    except Exception as e:
        self.handle_error(e, "SHOW_RATES")

def do_parser_status(self, _):
    """Показать статус парсера"""
    try:
        from ..parser_service.updater import RatesUpdater
        from ..parser_service.scheduler import ParserScheduler
        from ..parser_service.config import ParserConfig
        
        config = ParserConfig()
        updater = RatesUpdater(config)
        
        # Статус обновления
        status = updater.get_update_status()
        
        print(f"\n📊 Статус парсера курсов валют:")
        print(f"   Последнее обновление: {status.get('last_refresh', 'никогда')}")
        print(f"   Источник: {status.get('source', 'неизвестно')}")
        print(f"   Всего пар: {status['cache_status'].get('total', 0)}")
        print(f"   Актуальных: {status['cache_status'].get('fresh', 0)}")
        print(f"   Устаревших: {status['cache_status'].get('stale', 0)}")
        
        # Информация о конфигурации
        print(f"\n⚙️  Конфигурация:")
        print(f"   Базовая валюта: {config.BASE_FIAT_CURRENCY}")
        print(f"   TTL кэша: {config.CACHE_TTL_SECONDS} секунд")
        print(f"   Фиатные валюты: {len(config.FIAT_CURRENCIES)}")
        print(f"   Криптовалюты: {len(config.CRYPTO_CURRENCIES)}")
        print(f"   API ключ: {'установлен' if config.EXCHANGERATE_API_KEY != 'demo_key' else 'демо-ключ'}")
        
        # Проверка доступности источников
        print(f"\n🌐 Доступность источников:")
        
        from ..parser_service.api_clients import ApiClientFactory
        
        for source_name in ['coingecko', 'exchangerate']:
            try:
                client = ApiClientFactory.create_client(source_name, config)
                rates = client.fetch_rates()
                print(f"   {source_name.upper()}: ✅ доступен ({len(rates)} курсов)")
            except Exception as e:
                print(f"   {source_name.upper()}: ❌ недоступен ({str(e)[:50]}...)")
        
        # Пути к файлам
        print(f"\n📁 Файлы данных:")
        print(f"   Текущие курсы: {config.RATES_FILE}")
        print(f"   История: {config.EXCHANGE_RATES_FILE}")
        print(f"   Логи: {config.PARSER_LOG_FILE}")
        
    except Exception as e:
        self.handle_error(e, "PARSER_STATUS")

def do_start_parser(self, arg):
    """
    Запустить фоновый парсер
    Использование: start-parser [--interval <минуты>]
    """
    parser = argparse.ArgumentParser(prog='start-parser')
    parser.add_argument('--interval', 
                       type=int, 
                       default=5,
                       help='Интервал обновления в минутах')
    
    try:
        args = parser.parse_args(self.parse_args(arg))
    except SystemExit:
        return
    
    try:
        from ..parser_service.scheduler import ParserScheduler
        from ..parser_service.config import ParserConfig
        
        config = ParserConfig()
        scheduler = ParserScheduler(config)
        
        # Устанавливаем callback функции
        def on_update_start():
            print(f"\n🔄 Начато автоматическое обновление курсов...")
        
        def on_update_complete(result):
            print(f"✅ Автоматическое обновление завершено")
            print(f"   Обновлено курсов: {len(result.updated_pairs)}")
        
        def on_error(errors):
            print(f"❌ Ошибка при автоматическом обновлении:")
            for error in errors[:3]:  # Показываем первые 3 ошибки
                print(f"   - {error}")
        
        scheduler.set_callbacks(on_update_start, on_update_complete, on_error)
        
        # Запускаем планировщик
        scheduler.start(args.interval)
        
        print(f"\n🚀 Фоновый парсер запущен")
        print(f"   Интервал обновления: {args.interval} минут")
        print(f"   Базовая валюта: {config.BASE_FIAT_CURRENCY}")
        print(f"   TTL кэша: {config.CACHE_TTL_SECONDS} секунд")
        
        # Показываем статус
        status = scheduler.get_status()
        if status.get('next_run'):
            from datetime import datetime
            next_run = datetime.fromisoformat(status['next_run'])
            print(f"   Следующее обновление: {next_run.strftime('%H:%M:%S')}")
        
        print(f"\n💡 Используйте команды:")
        print(f"   - stop-parser - остановить парсер")
        print(f"   - parser-status - показать статус")
        print(f"   - update-rates - немедленное обновление")
        
    except Exception as e:
        self.handle_error(e, "START_PARSER")

def do_stop_parser(self, _):
    """Остановить фоновый парсер"""
    try:
        # В реальном приложении здесь будет сохранение состояния
        # и остановка планировщика
        print(f"\n🛑 Фоновый парсер остановлен")
        print(f"   Используйте 'start-parser' для повторного запуска")
        
    except Exception as e:
        self.handle_error(e, "STOP_PARSER")