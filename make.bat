@echo off
REM Windows equivalent of Makefile for ValutaTrade Hub

if "%1"=="install" goto install
if "%1"=="run" goto run
if "%1"=="lint" goto lint
if "%1"=="format" goto format
if "%1"=="test" goto test
if "%1"=="clean" goto clean
goto help

:install
echo Installing dependencies...
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe install --no-root
goto end

:run
echo Running ValutaTrade Hub...
set PYTHONIOENCODING=utf-8
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe run python -c "import sys; sys.path.insert(0, '.'); exec(open('main.py', encoding='utf-8').read())"
goto end

:lint
echo Running linter...
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe run ruff check .
goto end

:format
echo Formatting code...
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe run ruff format .
goto end

:test
echo Running tests...
C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\Scripts\poetry.exe run pytest tests/ -v --cov=valutatrade_hub --cov-report=html
goto end

:clean
echo Cleaning temporary files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
for %%f in (*.pyc) do del %%f
for %%f in (*.pyo) do del %%f
for %%f in (*.pyd) do del %%f
for %%f in (.coverage) do del %%f
if exist htmlcov rmdir /s /q htmlcov
if exist .pytest_cache rmdir /s /q .pytest_cache
if exist .ruff_cache rmdir /s /q .ruff_cache
if exist .mypy_cache rmdir /s /q .mypy_cache
goto end

:help
echo Available commands:
echo   make install    - Install dependencies
echo   make run        - Run the application
echo   make lint       - Run linter
echo   make format     - Format code
echo   make test       - Run tests
echo   make clean      - Clean temporary files
echo.
echo Usage: make.bat [command]
goto end

:end