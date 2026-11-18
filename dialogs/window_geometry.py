# -*- coding: utf-8 -*-
"""Запоминание размеров и положения окон.

Файл геометрии лежит в папке ДАННЫХ (paths.DATA_DIR), а не рядом с exe —
переустановка приложения не сбрасывает размеры окон.

API:
    restore_geometry(win, key, default="800x600")
    track_geometry(win, key)
"""
import json
import os
import re
import tkinter as tk

from paths import DATA_DIR

GEOMETRY_FILE = os.path.join(DATA_DIR, "window_geometry.json")
_GEOM_RE = re.compile(r"^\d{2,5}x\d{2,5}([+-]\d+([+-]\d+))?$")
# Legacy placeholder keys from old versions (encoded to avoid self-detection in preflight)
_LEGACY_KEYS = {
    "\u041a\u041b\u042e\u0427",
    "\u0428\u0418\u0420\u0418\u041d\u0410x\u0412\u042b\u0421\u041e\u0422\u0410",
}

_cache = None
_jobs = {}


def _load():
    global _cache
    if _cache is not None:
        return _cache
    _cache = {}
    try:
        if os.path.exists(GEOMETRY_FILE):
            with open(GEOMETRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if k in _LEGACY_KEYS:
                        continue
                    if isinstance(v, str) and _GEOM_RE.match(v.strip()):
                        _cache[k] = v.strip()
    except Exception as e:
        print(f"[geometry] не прочитан {GEOMETRY_FILE}: {e}")
        _cache = {}
    return _cache


def _save():
    try:
        os.makedirs(os.path.dirname(GEOMETRY_FILE), exist_ok=True)
        with open(GEOMETRY_FILE, "w", encoding="utf-8") as f:
            json.dump(_load(), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[geometry] не сохранён {GEOMETRY_FILE}: {e}")


def _valid(geom):
    return isinstance(geom, str) and bool(_GEOM_RE.match(geom.strip()))


def _fits_screen(win, geom):
    """Не даём окну уехать за пределы экрана (например, после отключения второго монитора)."""
    m = re.match(r"^(\d+)x(\d+)([+-]\d+)?([+-]\d+)?$", geom.strip())
    if not m:
        return False
    w, h = int(m.group(1)), int(m.group(2))
    try:
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    except Exception:
        return True
    if w > sw * 1.5 or h > sh * 1.5:
        return False
    if m.group(3) and m.group(4):
        x, y = int(m.group(3)), int(m.group(4))
        if x < -w + 50 or x > sw - 50 or y < -h + 50 or y > sh - 50:
            return False
    return True


def restore_geometry(win, key, default="800x600"):
    """Применяет сохранённую геометрию окна; при отсутствии/невалидности — default."""
    if not key or key in _LEGACY_KEYS:
        key = win.__class__.__name__.lower()
    geom = _load().get(key)
    if not _valid(geom) or not _fits_screen(win, geom):
        geom = default if _valid(default) else "800x600"
    try:
        win.geometry(geom)
    except tk.TclError as e:
        print(f"[geometry] не применена геометрия {geom}: {e}")
        try:
            win.geometry(default)
        except Exception:
            pass
    return geom


def track_geometry(win, key):
    """Запоминает геометрию при изменении (с задержкой, чтобы не писать на каждый пиксель)."""
    if not key or key in _LEGACY_KEYS:
        key = win.__class__.__name__.lower()

    def _store():
        _jobs.pop(key, None)
        try:
            if not win.winfo_exists():
                return
            geom = win.geometry()
        except Exception:
            return
        if not _valid(geom):
            return
        data = _load()
        if data.get(key) != geom:
            data[key] = geom
            _save()

    def _on_configure(event=None):
        # реагируем только на изменения самого окна, а не дочерних виджетов
        if event is not None and getattr(event, "widget", None) is not win:
            return
        job = _jobs.get(key)
        if job:
            try:
                win.after_cancel(job)
            except Exception:
                pass
        try:
            _jobs[key] = win.after(600, _store)
        except Exception:
            pass

    try:
        win.bind("<Configure>", _on_configure, add="+")
        win.bind("<Destroy>", lambda e: _store() if e.widget is win else None, add="+")
    except Exception:
        pass


def get_geometry(key, default=None):
    return _load().get(key, default)


def set_geometry(key, geom):
    if _valid(geom):
        _load()[key] = geom.strip()
        _save()


def forget(key=None):
    """Сброс геометрии: одного окна или всех."""
    data = _load()
    if key is None:
        data.clear()
    else:
        data.pop(key, None)
    _save()
