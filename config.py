import os
import re
import json

# Попытка импорта tkcalendar
try:
    from tkcalendar import Calendar
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

# Попытка импорта openpyxl
try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# Попытка импорта pdfplumber
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# Попытка импорта python-docx
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

# Константы
VERSION = "1.8.0"
BUILD_DATE = "30.09.2026"
DEFAULT_DB_NAME = "projects.db"
CONFIG_NAME = "config.json"
LOG_NAME = "project_log.txt"
BACKUP_DIR_NAME = "backups"
BACKUP_KEEP = 15            # сколько последних резервных копий БД хранить

# Папка программы: конфиг ищется рядом с app.py, а не в текущей папке запуска
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_CONFIG_FILE = os.path.join(APP_DIR, CONFIG_NAME)

DB_PATH = DEFAULT_DB_NAME
CONFIG_FILE = CONFIG_NAME
LOG_FILE = LOG_NAME
CURRENCIES = ["₽ (Рубли)", "€ (Евро)", "$ (Доллары)", "¥ (Юани)"]
TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]
ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB"]
PURCHASE_CURRENCIES = ["USD", "EUR", "RUB", "CNY"]

TURKISH_TIME_MAP = {
    "hafta": "Недели", "HAFTA": "Недели",
    "gün": "Календарные дни", "GÜN": "Календарные дни",
    "ay": "Месяцы", "AY": "Месяцы",
    "iş günü": "Рабочие дни", "İŞ GÜNÜ": "Рабочие дни",
    "işgünü": "Рабочие дни", "İŞGÜNÜ": "Рабочие дни",
}


def setup_paths(db_path):
    """Устанавливает глобальные пути к файлам.

    ВАЖНО: остальные модули должны читать пути через get_db_path()/get_log_file()
    (или config.DB_PATH), а не через `from config import DB_PATH` — такой импорт
    копирует значение один раз и не видит изменений.
    """
    global DB_PATH, CONFIG_FILE, LOG_FILE
    if not db_path:
        db_path = DEFAULT_DB_NAME
    db_path = os.path.expanduser(str(db_path))
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", db_path):
        # Путь вида «O:/...» из Windows-конфига при запуске на Linux —
        # используем базу рядом с программой
        db_path = os.path.join(APP_DIR, DEFAULT_DB_NAME)
    if not os.path.isabs(db_path):
        db_path = os.path.join(APP_DIR, db_path)
    DB_PATH = os.path.normpath(db_path)
    db_dir = os.path.dirname(DB_PATH) or APP_DIR
    CONFIG_FILE = os.path.join(db_dir, CONFIG_NAME)
    LOG_FILE = os.path.join(db_dir, LOG_NAME)
    return DB_PATH


def get_db_path():
    return DB_PATH


def get_log_file():
    return LOG_FILE


def get_backup_dir():
    return os.path.join(os.path.dirname(DB_PATH) or APP_DIR, BACKUP_DIR_NAME)


class ConfigManager:
    """Класс для управления конфигурацией"""
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = self.load_config()

    def load_config(self):
        default = {"db_path": DEFAULT_DB_NAME, "theme": "Light", "sort_by": "name"}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    return {**default, **json.load(f)}
            except Exception as e:
                print(f"Не удалось прочитать {self.config_file}: {e}")
        return default

    def save_config(self, config_file=None):
        try:
            with open(config_file or self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except OSError as e:
            print(f"Не удалось сохранить настройки в {config_file or self.config_file}: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()