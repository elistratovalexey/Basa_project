# -*- coding: utf-8 -*-
"""Конфигурация приложения: пути, константы, менеджер настроек.

Пути берутся из paths.py:
  программа (exe + библиотеки) — папка установки, заменяется при обновлении;
  данные — %APPDATA%\\BasaProject (настройки, кэши, локальная БД)
           %LOCALAPPDATA%\\BasaProject (логи, бэкапы, снимки синхронизации).
Переустановка приложения данные не затрагивает.
"""
import os
import json
import shutil
from datetime import datetime

from paths import (INSTALL_DIR, BUNDLE_DIR, DATA_DIR, LOCAL_DIR, APP_DIR,
                   CONFIG_DIR, LOG_DIR, BACKUP_DIR, SYNC_DIR,
                   LOCAL_CONFIG_FILE, DEFAULT_DB_PATH, PORTABLE,
                   migrate_legacy_data)

# Перенос данных из старой папки установки при первом запуске новой схемы
migrate_legacy_data()

<<<<<<< HEAD
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
=======
# === Константы приложения ===
VERSION = "1.8.0"
BUILD_DATE = "30.09.2026"
>>>>>>> eb530b97f2cefc0e88447bc32c25d0016fd68c35

DEFAULT_DB_NAME = "projects.db"
CONFIG_NAME = "config.json"
LOG_NAME = "project_log.txt"
BACKUP_KEEP = 15

CURRENCIES = ["₽ (Рубли)", "$ (Доллары)", "€ (Евро)", "¥ (Юани)", "₺ (Лира)"]
ORDER_CURRENCIES = ["EUR", "USD", "CNY", "RUB", "TRY"]
TIME_UNITS = ["Календарные дни", "Рабочие дни", "Недели", "Месяцы"]

DEFAULTS = {
    "db_path": DEFAULT_DB_PATH,
    "sort_by": "name",
    "sort_by_display": "По названию",
    "main_window_geometry": "",
    "app_version": VERSION,
}

# === Текущие рабочие пути (заполняются setup_paths) ===
DB_PATH = DEFAULT_DB_PATH
DB_DIR = DATA_DIR
CONFIG_FILE = os.path.join(DATA_DIR, CONFIG_NAME)
LOG_FILE = os.path.join(LOG_DIR, LOG_NAME)


def setup_paths(db_path):
    """Устанавливает рабочие пути по выбранной базе. Возвращает абсолютный путь к БД."""
    global DB_PATH, DB_DIR, CONFIG_FILE, LOG_FILE
    raw = str(db_path or DEFAULT_DB_NAME)
    p = os.path.abspath(os.path.expandvars(raw))
    if not os.path.isabs(p):
        p = os.path.join(DATA_DIR, raw)
    DB_PATH = p
    DB_DIR = os.path.dirname(p) or DATA_DIR
    CONFIG_FILE = os.path.join(DB_DIR, CONFIG_NAME)   # копия настроек рядом с БД
    LOG_FILE = os.path.join(LOG_DIR, LOG_NAME)        # журнал — в папке данных
    return DB_PATH


def get_db_path():
    return DB_PATH


def get_log_file():
    return LOG_FILE


def get_backup_dir():
    return BACKUP_DIR


def get_config_file():
    return CONFIG_FILE


class ConfigManager:
    """Настройки пользователя. Живут в папке данных, а не рядом с exe."""

    def __init__(self, path=None):
        self.path = path or LOCAL_CONFIG_FILE
        self.config = dict(DEFAULTS)
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            self.save()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.config.update(data)
        except Exception as e:
            # битый конфиг не должен ронять приложение — откладываем копию и стартуем с дефолтов
            try:
                bad = self.path + ".bad_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy2(self.path, bad)
                print(f"[config] конфиг повреждён ({e}), копия: {bad}")
            except Exception:
                print(f"[config] конфиг повреждён: {e}")
            self.config = dict(DEFAULTS)
            self.save()

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[config] не удалось сохранить {self.path}: {e}")

    def save_config(self, path=None):
        """Копия настроек (например, рядом с базой — для переноса на другой ПК)."""
        dst = path or self.path
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[config] не удалось сохранить копию {dst}: {e}")
