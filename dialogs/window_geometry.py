# -*- coding: utf-8 -*-
"""Сохранение размеров/позиций окон между запусками программы."""
import os
import json

_GEOM_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "window_geometry.json")


def _load():
    try:
        with open(_GEOM_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    try:
        with open(_GEOM_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def restore_geometry(window, key, default=None):
    """Восстановить размер/позицию окна по ключу."""
    geom = _load().get(key) or default
    if geom:
        try:
            window.geometry(geom)
        except Exception:
            pass


def track_geometry(window, key):
    """Автосохранение геометрии при ручном ресайзе/перемещении (с задержкой 1.5 с)."""
    state = {"timer": None}

    def _do_save():
        state["timer"] = None
        try:
            if not window.winfo_exists():
                return
            data = _load()
            data[key] = window.geometry()
            _save(data)
        except Exception:
            pass

    def _on_configure(event):
        if event.widget is not window:
            return
        if state["timer"] is not None:
            try:
                window.after_cancel(state["timer"])
            except Exception:
                pass
        try:
            state["timer"] = window.after(1500, _do_save)
        except Exception:
            pass

    def _on_destroy(event):
        if event.widget is window:
            if state["timer"] is not None:
                try:
                    window.after_cancel(state["timer"])
                except Exception:
                    pass
            _do_save()

    window.bind("<Configure>", _on_configure)
    window.bind("<Destroy>", _on_destroy)