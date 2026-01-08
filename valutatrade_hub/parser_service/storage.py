# valutatrade_hub/parser_service/storage.py
"""
Модуль для работы с хранилищем курсов валют.
"""
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import shutil

from ..core.exceptions import DatabaseError
from .config import ParserConfig


class RatesStorage:
    """Хранилище для курсов валют."""
    
    def __init__(self, config: ParserConfig):
        self.config = config
        self.rates_file = config.get_rate_file_path()
        self.history_file = config.get_exchange_rates_file_path()
        
        # Создаем директории, если они не существуют
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """Создать необходимые директории."""
        try:
            # Директория для данных
            data_dir = Path(self.config.DATA_DIR)
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Директория для логов
            logs_dir = Path(self.config.PARSER_LOG_FILE).parent
            logs_dir.mkdir(parents=True, exist_ok=True)
            
        except Exception as e:
            raise DatabaseError(f"Не удалось создать директории: {e}")
    
    def save_current_rates(
        self, 
        rates: Dict[str, float],
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Сохранить текущие курсы в rates.json.
        
        Args:
            rates: Словарь курсов {pair: rate}
            source: Источник данных
            metadata: Дополнительные метаданные
        """
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            # Структура данных для rates.json
            rates_data = {
                "pairs": {},
                "metadata": {
                    "last_refresh": timestamp,
                    "source": source,
                    "updated_by": "parser_service",
                    "total_pairs": len(rates)
                }
            }
            
            # Заполняем пары
            for pair_key, rate in rates.items():
                rates_data["pairs"][pair_key] = {
                    "rate": rate,
                    "updated_at": timestamp,
                    "source": source
                }
            
            # Добавляем метаданные, если есть
            if metadata:
                rates_data["metadata"].update(metadata)
            
            # Атомарная запись в файл
            self._atomic_write(self.rates_file, rates_data)
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при сохранении текущих курсов: {e}")
    
    def save_to_history(
        self,
        rates: Dict[str, float],
        source: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Сохранить курсы в историческое хранилище (exchange_rates.json).
        
        Args:
            rates: Словарь курсов {pair: rate}
            source: Источник данных
            metadata: Дополнительные метаданные
        """
        try:
            timestamp = datetime.utcnow().isoformat() + "Z"
            history_data = self._load_history()
            
            # Добавляем каждую пару в историю
            for pair_key, rate in rates.items():
                # Создаем уникальный ID
                record_id = f"{pair_key}_{timestamp.replace(':', '-').replace('.', '-')}"
                
                record = {
                    "id": record_id,
                    "from_currency": pair_key.split("_")[0],
                    "to_currency": pair_key.split("_")[1],
                    "rate": rate,
                    "timestamp": timestamp,
                    "source": source,
                    "meta": metadata or {}
                }
                
                # Добавляем запись в историю
                history_data.append(record)
            
            # Сохраняем историю
            self._atomic_write(self.history_file, history_data)
            
            # Ограничиваем размер истории (сохраняем последние 1000 записей)
            self._trim_history(1000)
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при сохранении в историю: {e}")
    
    def load_current_rates(self) -> Dict[str, Any]:
        """
        Загрузить текущие курсы из rates.json.
        
        Returns:
            Данные текущих курсов
        """
        try:
            if not self.rates_file.exists():
                return {"pairs": {}, "metadata": {}}
            
            with open(self.rates_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data
            
        except json.JSONDecodeError as e:
            raise DatabaseError(f"Ошибка декодирования JSON файла {self.rates_file}: {e}")
        except Exception as e:
            raise DatabaseError(f"Ошибка при загрузке текущих курсов: {e}")
    
    def load_history(
        self, 
        limit: Optional[int] = None,
        currency_pair: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Загрузить исторические данные.
        
        Args:
            limit: Ограничение количества записей
            currency_pair: Фильтр по паре валют (например, "BTC_USD")
            
        Returns:
            Список исторических записей
        """
        try:
            history = self._load_history()
            
            # Применяем фильтр по паре, если указан
            if currency_pair:
                history = [record for record in history 
                          if record.get("from_currency") == currency_pair.split("_")[0]
                          and record.get("to_currency") == currency_pair.split("_")[1]]
            
            # Сортируем по времени (новые первыми)
            history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            
            # Применяем лимит, если указан
            if limit:
                history = history[:limit]
            
            return history
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при загрузке истории: {e}")
    
    def get_rate(self, currency_pair: str) -> Optional[Dict[str, Any]]:
        """
        Получить последний курс для указанной пары.
        
        Args:
            currency_pair: Пара валют (например, "BTC_USD")
            
        Returns:
            Информация о курсе или None если не найден
        """
        try:
            rates_data = self.load_current_rates()
            pairs = rates_data.get("pairs", {})
            
            if currency_pair in pairs:
                return pairs[currency_pair]
            
            return None
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при получении курса для пары {currency_pair}: {e}")
    
    def is_rate_fresh(self, currency_pair: str) -> bool:
        """
        Проверить актуальность курса.
        
        Args:
            currency_pair: Пара валют
            
        Returns:
            True если курс актуален (моложе TTL)
        """
        try:
            rate_info = self.get_rate(currency_pair)
            if not rate_info:
                return False
            
            updated_at_str = rate_info.get("updated_at")
            if not updated_at_str:
                return False
            
            # Преобразуем строку в datetime
            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
            current_time = datetime.utcnow()
            
            # Проверяем, не устарел ли курс
            age = (current_time - updated_at).total_seconds()
            return age <= self.config.CACHE_TTL_SECONDS
            
        except Exception:
            return False
    
    def get_all_pairs(self) -> List[str]:
        """
        Получить список всех пар, для которых есть курсы.
        
        Returns:
            Список пар валют
        """
        try:
            rates_data = self.load_current_rates()
            pairs = list(rates_data.get("pairs", {}).keys())
            return pairs
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при получении списка пар: {e}")
    
    def clear_history(self) -> None:
        """Очистить историю курсов."""
        try:
            if self.history_file.exists():
                self.history_file.unlink()
        except Exception as e:
            raise DatabaseError(f"Ошибка при очистке истории: {e}")
    
    def backup(self, backup_dir: str = "backups") -> Path:
        """
        Создать резервную копию данных.
        
        Args:
            backup_dir: Директория для бэкапов
            
        Returns:
            Путь к созданному бэкапу
        """
        try:
            backup_path = Path(backup_dir)
            backup_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = backup_path / f"rates_backup_{timestamp}.json"
            
            # Копируем текущие курсы
            if self.rates_file.exists():
                shutil.copy2(self.rates_file, backup_file)
            
            return backup_file
            
        except Exception as e:
            raise DatabaseError(f"Ошибка при создании бэкапа: {e}")
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """Загрузить исторические данные из файла."""
        try:
            if not self.history_file.exists():
                return []
            
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                return data
            else:
                return []
                
        except json.JSONDecodeError:
            # Если файл поврежден, возвращаем пустой список
            return []
        except Exception:
            return []
    
    def _atomic_write(self, file_path: Path, data: Any) -> None:
        """
        Атомарная запись в файл (через временный файл).
        
        Args:
            file_path: Путь к файлу
            data: Данные для записи
        """
        # Создаем временный файл
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=file_path.parent,
            delete=False,
            suffix='.tmp'
        ) as tmp_file:
            json.dump(data, tmp_file, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)
        
        try:
            # Перемещаем временный файл в целевой
            tmp_path.replace(file_path)
        except Exception as e:
            # Если ошибка, удаляем временный файл
            if tmp_path.exists():
                tmp_path.unlink()
            raise DatabaseError(f"Ошибка атомарной записи: {e}")
    
    def _trim_history(self, max_records: int) -> None:
        """
        Обрезать историю до указанного количества записей.
        
        Args:
            max_records: Максимальное количество записей
        """
        try:
            history = self._load_history()
            
            if len(history) > max_records:
                # Сортируем по времени (старые первыми)
                history.sort(key=lambda x: x.get("timestamp", ""))
                # Оставляем только последние max_records записей
                history = history[-max_records:]
                # Сохраняем обрезанную историю
                self._atomic_write(self.history_file, history)
                
        except Exception as e:
            raise DatabaseError(f"Ошибка при обрезке истории: {e}")