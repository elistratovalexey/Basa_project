# -*- coding: utf-8 -*-
"""Единая схема путей приложения.

Программа (exe + библиотеки) lives в папке установки — её можно заменять/удалять.
Данные пользователя:
  %APPDATA%\BasaProject        — настройки, кэши, локальная БД
  %LOCALAPPDATA%\BasaProject   — логи, резервные копии, снимки синхронизации
Переустановка приложения данные не затрагивает.

Портативный режим: положите portable.txt рядом с exe — данные останутся в папке программы.
"""
import os
import shutil
import sys

APP_NAME = "BasaProject"
FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    INSTALL_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = getattr(sys, "_MEIPASS", INSTALL_DIR)
else:
    INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = INSTALL_DIR

PORTABLE = os.path.exists(os.path.join(INSTALL_DIR, "portable.txt"))

if PORTABLE or not FROZEN:
    DATA_DIR = INSTALL_DIR
    LOCAL_DIR = INSTALL_DIR
else:
    _roaming = os.environ.get("APPDATA") or os.path.expanduser("~")
    _local = os.environ.get("LOCALAPPDATA") or _roaming
    DATA_DIR = os.path.join(_roaming, APP_NAME)
    LOCAL_DIR = os.path.join(_local, APP_NAME)

CONFIG_DIR = DATA_DIR
LOG_DIR = os.path.join(LOCAL_DIR, "logs")
BACKUP_DIR = os.path.join(LOCAL_DIR, "backups")
SYNC_DIR = os.path.join(LOCAL_DIR, "cloud_sync")

APP_DIR = DATA_DIR                                    # совместимость со старым кодом
LOCAL_CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "projects.db")

for _d in (DATA_DIR, LOCAL_DIR, LOG_DIR, BACKUP_DIR, SYNC_DIR):
    try:
        os.makedirs(_d, exist_ok=True)
    except OSError as e:
        print(f"[paths] не создана папка {_d}: {e}")

LEGACY_FILES = ("config.json", "window_geometry.json", "translation_cache.json",
                "cloud_config.json", "projects.db")
LEGACY_DIRS = {"logs": LOG_DIR, "backups": BACKUP_DIR, "cloud_sync": SYNC_DIR}


def _copy_if_absent(src, dst):
    """Копирует, только если источника есть, а приёмника ещё нет."""
    if not os.path.isfile(src) or os.path.exists(dst):
        return False
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except OSError as e:
        print(f"[paths] не скопирован {src}: {e}")
        return False


def migrate_from(old_dir, verbose=True):
    """Перенос данных из указанной старой папки установки."""
    old_dir = os.path.abspath(old_dir)
    if not os.path.isdir(old_dir):
        return 0
    if os.path.normcase(old_dir) == os.path.normcase(DATA_DIR):
        return 0
    moved = 0
    for name in LEGACY_FILES:
        dst = DEFAULT_DB_PATH if name == "projects.db" else os.path.join(CONFIG_DIR, name)
        if _copy_if_absent(os.path.join(old_dir, name), dst):
            moved += 1
            if verbose:
                print(f"[paths] перенесён {name}")
    for sub, dst_dir in LEGACY_DIRS.items():
        src_dir = os.path.join(old_dir, sub)
        if not os.path.isdir(src_dir):
            continue
        for root, _dirs, files in os.walk(src_dir):
            rel = os.path.relpath(root, src_dir)
            for f in files:
                s = os.path.join(root, f)
                d = os.path.join(dst_dir, f) if rel == "." else os.path.join(dst_dir, rel, f)
                if _copy_if_absent(s, d):
                    moved += 1
    if verbose and moved:
        print(f"[paths] перенос из {old_dir}: файлов {moved}")
    return moved


def migrate_legacy_data():
    """Автоперенос при первом запуске после смены схемы путей."""
    if PORTABLE or not FROZEN:
        return 0
    total = migrate_from(INSTALL_DIR)
    marker = os.path.join(CONFIG_DIR, ".migrated")
    if not os.path.exists(marker):
        try:
            with open(marker, "w", encoding="utf-8") as f:
                f.write("legacy data migrated\n")
        except OSError:
            pass
    return total


def describe():
    return (f"install : {INSTALL_DIR}\n"
            f"data    : {DATA_DIR}\n"
            f"local   : {LOCAL_DIR}\n"
            f"portable: {PORTABLE}")
