# valutatrade_hub/infra/database.py
import json
import os
import threading
from typing import Any, Dict, List, Optional, TypeVar, Generic
from datetime import datetime
from pathlib import Path
from ..core.exceptions import DatabaseError
from ..infra.settings import SettingsLoader, SingletonMeta

T = TypeVar('T')


class DatabaseManager(metaclass=SingletonMeta):
    """
    Менеджер базы данных.
    Singleton для управления операциями с JSON-хранилищем.
    """
    
    def __init__(self):
        """Инициализация менеджера БД"""
        if hasattr(self, '_initialized'):
            return
        
        self.settings = SettingsLoader()
        self._lock = threading.RLock()  # Reentrant lock для потокобезопасности
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._cache_ttl = 60  # 60 секунд TTL для кэша
        self._initialized = True
    
    def _get_file_path(self, filename: str) -> str:
        """Получить полный путь к файлу"""
        data_dir = self.settings.get('paths.data_dir', 'data')
        return os.path.join(data_dir, filename)
    
    def _read_file(self, filepath: str) -> Any:
        """Прочитать файл с блокировкой"""
        with self._lock:
            try:
                if not os.path.exists(filepath):
                    # Возвращаем структуру по умолчанию
                    if 'users' in filepath or 'portfolios' in filepath or 'transactions' in filepath:
                        return []
                    else:
                        return {}
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise DatabaseError(f"Ошибка декодирования JSON файла {filepath}: {e}")
            except Exception as e:
                raise DatabaseError(f"Ошибка чтения файла {filepath}: {e}")
    
    def _write_file(self, filepath: str, data: Any) -> None:
        """Записать файл с блокировкой"""
        with self._lock:
            try:
                # Создаем директорию, если ее нет
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                # Сериализация данных
                def default_serializer(obj):
                    if isinstance(obj, datetime):
                        return obj.isoformat()
                    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, default=default_serializer, ensure_ascii=False)
                
                # Инвалидируем кэш для этого файла
                if filepath in self._cache:
                    del self._cache[filepath]
                    del self._cache_timestamps[filepath]
                    
            except Exception as e:
                raise DatabaseError(f"Ошибка записи файла {filepath}: {e}")
    
    def _get_cached_data(self, filepath: str) -> Optional[Any]:
        """Получить данные из кэша"""
        with self._lock:
            current_time = datetime.now().timestamp()
            
            if filepath in self._cache:
                cache_time = self._cache_timestamps.get(filepath, 0)
                if current_time - cache_time < self._cache_ttl:
                    return self._cache[filepath]
            
            return None
    
    def _set_cached_data(self, filepath: str, data: Any) -> None:
        """Сохранить данные в кэш"""
        with self._lock:
            self._cache[filepath] = data
            self._cache_timestamps[filepath] = datetime.now().timestamp()
    
    def read_data(self, filename: str, use_cache: bool = True) -> Any:
        """
        Прочитать данные из файла
        
        Args:
            filename: Имя файла (например, 'users.json')
            use_cache: Использовать кэширование
        
        Returns:
            Данные из файла
        """
        filepath = self._get_file_path(filename)
        
        if use_cache:
            cached_data = self._get_cached_data(filepath)
            if cached_data is not None:
                return cached_data
        
        data = self._read_file(filepath)
        
        if use_cache:
            self._set_cached_data(filepath, data)
        
        return data
    
    def write_data(self, filename: str, data: Any) -> None:
        """
        Записать данные в файл
        
        Args:
            filename: Имя файла
            data: Данные для записи
        """
        filepath = self._get_file_path(filename)
        self._write_file(filepath, data)
    
    def update_data(self, filename: str, updater_func, *args, **kwargs) -> Any:
        """
        Атомарное обновление данных
        
        Args:
            filename: Имя файла
            updater_func: Функция для обновления данных
            *args, **kwargs: Аргументы для updater_func
        
        Returns:
            Результат выполнения updater_func
        """
        with self._lock:
            data = self.read_data(filename, use_cache=False)
            result = updater_func(data, *args, **kwargs)
            self.write_data(filename, data)
            return result
    
    def find_one(self, filename: str, predicate) -> Optional[Any]:
        """
        Найти один элемент по предикату
        
        Args:
            filename: Имя файла
            predicate: Функция-предикат
        
        Returns:
            Первый найденный элемент или None
        """
        data = self.read_data(filename)
        
        if isinstance(data, list):
            for item in data:
                if predicate(item):
                    return item
        elif isinstance(data, dict):
            for key, value in data.items():
                if predicate(value):
                    return value
        
        return None
    
    def find_all(self, filename: str, predicate) -> List[Any]:
        """
        Найти все элементы по предикату
        
        Args:
            filename: Имя файла
            predicate: Функция-предикат
        
        Returns:
            Список найденных элементов
        """
        data = self.read_data(filename)
        results = []
        
        if isinstance(data, list):
            for item in data:
                if predicate(item):
                    results.append(item)
        elif isinstance(data, dict):
            for value in data.values():
                if predicate(value):
                    results.append(value)
        
        return results
    
    def insert(self, filename: str, item: Any) -> Any:
        """
        Вставить новый элемент
        
        Args:
            filename: Имя файла
            item: Элемент для вставки
        
        Returns:
            Вставленный элемент
        """
        def updater(data):
            if isinstance(data, list):
                data.append(item)
            elif isinstance(data, dict):
                # Для словаря требуется ключ
                if hasattr(item, 'id'):
                    data[item.id] = item
                else:
                    raise DatabaseError("Для вставки в словарь требуется элемент с атрибутом 'id'")
            return item
        
        return self.update_data(filename, updater)
    
    def update(self, filename: str, predicate, updater_func) -> Optional[Any]:
        """
        Обновить элемент по предикату
        
        Args:
            filename: Имя файла
            predicate: Функция-предикат для поиска элемента
            updater_func: Функция для обновления элемента
        
        Returns:
            Обновленный элемент или None
        """
        def bulk_updater(data):
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if predicate(item):
                        data[i] = updater_func(item)
                        return data[i]
            elif isinstance(data, dict):
                for key, value in data.items():
                    if predicate(value):
                        data[key] = updater_func(value)
                        return data[key]
            return None
        
        return self.update_data(filename, bulk_updater)
    
    def delete(self, filename: str, predicate) -> bool:
        """
        Удалить элемент по предикату
        
        Args:
            filename: Имя файла
            predicate: Функция-предикат
        
        Returns:
            True если элемент удален, иначе False
        """
        def updater(data):
            if isinstance(data, list):
                for i, item in enumerate(data):
                    if predicate(item):
                        data.pop(i)
                        return True
            elif isinstance(data, dict):
                keys_to_delete = []
                for key, value in data.items():
                    if predicate(value):
                        keys_to_delete.append(key)
                
                for key in keys_to_delete:
                    del data[key]
                
                return len(keys_to_delete) > 0
            return False
        
        return self.update_data(filename, updater)
    
    def clear_cache(self) -> None:
        """Очистить кэш"""
        with self._lock:
            self._cache.clear()
            self._cache_timestamps.clear()