# Makefile
.PHONY: install run build publish package-install lint format clean test

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
	poetry run pytest

clean:
	rm -rf build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +