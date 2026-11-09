# -*- coding: utf-8 -*-
"""
terminal_log.py — дублирует ВЕСЬ вывод терминала (print, traceback, warnings)
в отдельный файл logs/terminal_ГГГГ-ММ-ДД.log.

Файл открывается в режиме добавления: история всех запусков сохраняется.
Каждая сессия помечается заголовком с датой/временем старта и завершения.
Буферизация построчная — записи не теряются даже при падении программы.
"""
import sys
import os
import datetime


class _TeeStream:
    """Пишет одновременно в оригинальный поток (терминал) и в файл."""

    def __init__(self, original, file_handle):
        self._original = original
        self._file = file_handle

    def write(self, data):
        try:
            self._original.write(data)
        except Exception:
            pass
        try:
            self._file.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
        try:
            self._file.flush()
        except Exception:
            pass

    def isatty(self):
        try:
            return self._original.isatty()
        except Exception:
            return False

    def fileno(self):
        return self._original.fileno()

    def __getattr__(self, name):
        return getattr(self._original, name)


_file_handle = None
_log_path = None
_installed = False


def install(log_dir=None):
    """Включает дублирование вывода терминала в файл. Вызывать один раз при старте."""
    global _file_handle, _log_path, _installed
    if _installed:
        return _log_path
    try:
        if log_dir is None:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        _log_path = os.path.join(
            log_dir, f"terminal_{datetime.date.today().isoformat()}.log")
        _file_handle = open(_log_path, "a", encoding="utf-8", buffering=1)
        _file_handle.write(
            f"\n===== СЕССИЯ ЗАПУЩЕНА {datetime.datetime.now():%d.%m.%Y %H:%M:%S} =====\n")
        _file_handle.flush()
        sys.stdout = _TeeStream(sys.stdout, _file_handle)
        sys.stderr = _TeeStream(sys.stderr, _file_handle)
        _installed = True
    except Exception as e:
        # Если лог не пишется — программа продолжает работать как раньше
        try:
            sys.__stdout__.write(f"[terminal_log] не удалось включить лог: {e}\n")
        except Exception:
            pass
    return _log_path


def get_path():
    """Путь к файлу лога текущей сессии (для кнопки/открытия)."""
    return _log_path


def session_end():
    """Помечает конец сессии в файле (вызывать при закрытии приложения)."""
    global _file_handle
    if _file_handle:
        try:
            _file_handle.write(
                f"===== СЕССИЯ ЗАВЕРШЕНА {datetime.datetime.now():%d.%m.%Y %H:%M:%S} =====\n")
            _file_handle.flush()
        except Exception:
            pass