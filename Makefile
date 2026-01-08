.PHONY: install run build publish package-install lint format test clean init-dirs logs

install:
	poetry install

run:
	poetry run valutatrade

build:
	poetry build

publish:
	poetry publish --dry-run

package-install:
	pip install dist/*.whl

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

test:
	poetry run pytest tests/ -v --cov=valutatrade_hub --cov-report=html

test-unit:
	poetry run pytest tests/unit -v

test-integration:
	poetry run pytest tests/integration -v

clean:
	rm -rf build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov .pytest_cache .ruff_cache .mypy_cache

init-dirs:
	mkdir -p data logs config tests/unit tests/integration

logs:
	tail -f logs/valutatrade.log

watch:
	poetry run ruff check . --watch

type-check:
	poetry run mypy valutatrade_hub/

security-check:
	poetry run bandit -r valutatrade_hub/

docs:
	@echo "Генерация документации..."
	poetry run pdoc --html valutatrade_hub --output-dir docs

profile:
	poetry run python -m cProfile -o profile.stats main.py

docker-build:
	docker build -t valutatrade .

docker-run:
	docker run -it --rm valutatrade

help:
	@echo "Доступные команды:"
	@echo "  install        - Установить зависимости"
	@echo "  run            - Запустить приложение"
	@echo "  build          - Собрать пакет"
	@echo "  lint           - Проверить код линтером"
	@echo "  format         - Отформатировать код"
	@echo "  test           - Запустить все тесты"
	@echo "  test-unit      - Запустить unit-тесты"
	@echo "  test-integration - Запустить интеграционные тесты"
	@echo "  clean          - Очистить временные файлы"
	@echo "  init-dirs      - Создать необходимые директории"
	@echo "  logs           - Просмотр логов в реальном времени"
	@echo "  type-check     - Проверка типов с помощью mypy"
	@echo "  security-check - Проверка безопасности кода"
	@echo "  docs           - Сгенерировать документацию"