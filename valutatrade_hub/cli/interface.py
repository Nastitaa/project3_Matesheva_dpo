# valutatrade_hub/cli/interface.py
import cmd
import sys
from typing import Optional
from prettytable import PrettyTable
from ..core.usecases import UserManager, PortfolioManager, ExchangeRateService
from ..core.models import User


class ValutaTradeCLI(cmd.Cmd):
    """Консольный интерфейс для торговли валютами"""

    intro = "Добро пожаловать в ValutaTrade Hub! Введите help для списка команд."
    prompt = "(valutatrade) "

    def __init__(self):
        super().__init__()
        self.user_manager = UserManager()
        self.portfolio_manager = PortfolioManager()
        self.exchange_service = ExchangeRateService()
        self.current_user: Optional[User] = None

    def do_register(self, arg):
        """Зарегистрировать нового пользователя: register <имя> <пароль>"""
        args = arg.split()
        if len(args) != 2:
            print("Использование: register <имя> <пароль>")
            return

        username, password = args
        try:
            user = self.user_manager.register_user(username, password)
            print(f"Пользователь {username} успешно зарегистрирован (ID: {user.user_id})")
        except ValueError as e:
            print(f"Ошибка: {e}")

    def do_login(self, arg):
        """Войти в систему: login <имя> <пароль>"""
        args = arg.split()
        if len(args) != 2:
            print("Использование: login <имя> <пароль>")
            return

        username, password = args
        user = self.user_manager.authenticate_user(username, password)

        if user:
            self.current_user = user
            print(f"Добро пожаловать, {username}!")
            self.prompt = f"({username}) "
        else:
            print("Неверное имя пользователя или пароль")

    def do_logout(self, _):
        """Выйти из системы"""
        if self.current_user:
            print(f"До свидания, {self.current_user.username}!")
            self.current_user = None
            self.prompt = "(valutatrade) "
        else:
            print("Вы не вошли в систему")

    def do_balance(self, _):
        """Показать баланс портфеля"""
        if not self.current_user:
            print("Сначала войдите в систему")
            return

        portfolio = self.portfolio_manager.get_user_portfolio(self.current_user.user_id)

        table = PrettyTable()
        table.field_names = ["Валюта", "Баланс", "В USD"]
        table.align["Валюта"] = "l"
        table.align["Баланс"] = "r"
        table.align["В USD"] = "r"

        total_usd = 0
        for currency, wallet in portfolio.wallets.items():
            rate = self.exchange_service.get_rate(currency, "USD") or 1.0
            value_usd = wallet.balance * rate
            total_usd += value_usd

            table.add_row([currency, f"{wallet.balance:.2f}", f"${value_usd:.2f}"])

        print(table)
        print(f"\nОбщая стоимость портфеля: ${total_usd:.2f}")

    def do_deposit(self, arg):
        """Пополнить баланс: deposit <валюта> <сумма>"""
        if not self.current_user:
            print("Сначала войдите в систему")
            return

        args = arg.split()
        if len(args) != 2:
            print("Использование: deposit <валюта> <сумма>")
            return

        currency, amount_str = args
        try:
            amount = float(amount_str)
            if amount <= 0:
                print("Сумма должна быть положительной")
                return

            portfolio = self.portfolio_manager.get_user_portfolio(self.current_user.user_id)
            wallet = portfolio.get_wallet(currency.upper())

            if not wallet:
                portfolio.add_currency(currency.upper())
                wallet = portfolio.get_wallet(currency.upper())

            wallet.deposit(amount)
            self.portfolio_manager._save_portfolios()
            print(f"Успешно пополнено {amount:.2f} {currency.upper()}")

        except ValueError as e:
            print(f"Ошибка: {e}")
        except Exception as e:
            print(f"Ошибка при пополнении: {e}")

    def do_buy(self, arg):
        """Купить валюту: buy <валюта> <сумма в USD>"""
        self._execute_trade(arg, "USD")

    def do_sell(self, arg):
        """Продать валюту: sell <валюта> <сумма>"""
        args = arg.split()
        if len(args) != 2:
            print("Использование: sell <валюта> <сумма>")
            return

        currency, amount_str = args
        self._execute_trade(f"{currency} {amount_str} USD", currency)

    def _execute_trade(self, arg: str, from_currency: str):
        """Выполнить обмен валюты"""
        if not self.current_user:
            print("Сначала войдите в систему")
            return

        args = arg.split()
        if len(args) != 2:
            print(f"Использование: {from_currency.lower()} <валюта> <сумма>")
            return

        to_currency, amount_str = args

        try:
            amount = float(amount_str)
            if amount <= 0:
                print("Сумма должна быть положительной")
                return

            rate = self.exchange_service.get_rate(from_currency, to_currency.upper())
            if not rate:
                print(f"Курс для пары {from_currency}/{to_currency} не найден")
                return

            print(f"Курс: 1 {from_currency} = {rate:.4f} {to_currency.upper()}")
            print(f"Вы получите: {amount * rate:.4f} {to_currency.upper()}")

            confirm = input("Подтвердить сделку? (yes/no): ")
            if confirm.lower() != "yes":
                print("Сделка отменена")
                return

            success = self.portfolio_manager.execute_trade(
                self.current_user.user_id, from_currency, to_currency.upper(), amount, rate
            )

            if success:
                print("Сделка успешно выполнена!")
            else:
                print("Недостаточно средств для выполнения сделки")

        except ValueError as e:
            print(f"Ошибка: {e}")
        except Exception as e:
            print(f"Ошибка при выполнении сделки: {e}")

    def do_rates(self, arg):
        """Показать курсы валют: rates [базовая валюта]"""
        base_currency = arg.upper() if arg else "USD"

        if base_currency not in self.exchange_service.rates:
            print(f"Курсы для валюты {base_currency} не найдены")
            return

        table = PrettyTable()
        table.field_names = ["Валюта", f"Курс к {base_currency}"]
        table.align["Валюта"] = "l"
        table.align[f"Курс к {base_currency}"] = "r"

        rates = self.exchange_service.rates.get(base_currency, {})
        for currency, rate in rates.items():
            table.add_row([currency, f"{rate:.4f}"])

        print(table)

    def do_profile(self, _):
        """Показать профиль пользователя"""
        if not self.current_user:
            print("Сначала войдите в систему")
            return

        print(self.current_user.get_user_info())

    def do_exit(self, _):
        """Выйти из приложения"""
        print("До свидания!")
        return True

    def do_quit(self, _):
        """Выйти из приложения"""
        return self.do_exit(_)

    def default(self, line):
        print(f"Неизвестная команда: {line}")
        print("Введите help для списка команд")

    def emptyline(self):
        pass


def main():
    """Точка входа в CLI"""
    cli = ValutaTradeCLI()
    cli.cmdloop()
