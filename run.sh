#!/bin/bash
# ============================================================
#  Запуск программы "База проектов" в фоне
#   - защита от повторного запуска
#   - явный интерпретатор из venv (не системный python3)
#   - проверка зависимостей ДО старта
#   - лог запуска: logs/launch.log
# ============================================================

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$APP_DIR" || exit 1

LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"
LAUNCH_LOG="$LOG_DIR/launch.log"

log()    { printf '[%s] %s\n' "$(date '+%d.%m.%Y %H:%M:%S')" "$*" >> "$LAUNCH_LOG"; }
notify() { command -v notify-send >/dev/null 2>&1 && notify-send "$@" 2>/dev/null; }

# --- 1. Графическая сессия обязательна (Tkinter) ---
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    log "ОШИБКА: нет DISPLAY/WAYLAND_DISPLAY — запуск без графики невозможен"
    notify -u critical "База проектов" "Нет графической сессии. Запустите из рабочего стола."
    exit 1
fi

# --- 2. Защита от второго экземпляра ---
if pgrep -f "$APP_DIR/app.py" >/dev/null 2>&1; then
    log "Повторный запуск отклонён: программа уже работает"
    notify "База проектов" "Программа уже запущена"
    exit 0
fi

# --- 3. Интерпретатор: venv важнее системного ---
if [ -x "$APP_DIR/venv/bin/python" ]; then
    PY="$APP_DIR/venv/bin/python"
else
    PY="$(command -v python3)"
fi
if [ -z "$PY" ]; then
    log "ОШИБКА: python3 не найден"
    notify -u critical "База проектов" "Python не найден"
    exit 1
fi
if ! "$PY" -V >/dev/null 2>&1; then
    log "ОШИБКА: интерпретатор $PY не запускается (битый venv после обновления Python)"
    notify -u critical "База проектов" "Сломан venv. Пересоздайте окружение."
    exit 1
fi

# --- 4. Кодировка, локаль, изоляция от user-site чужой версии Python ---
export PYTHONIOENCODING=utf-8
export PYTHONNOUSERSITE=1
if locale -a 2>/dev/null | grep -qiE '^ru_RU\.(utf8|UTF-8)$'; then
    export LANG=ru_RU.UTF-8
else
    export LANG=C.UTF-8
fi

# --- 5. Наличие приложения ---
if [ ! -f "$APP_DIR/app.py" ]; then
    log "ОШИБКА: не найден $APP_DIR/app.py"
    notify -u critical "База проектов" "Файл app.py не найден"
    exit 1
fi

# --- 6. Проверка зависимостей ДО запуска ---
MISSING="$("$PY" - <<'PYEOF'
import importlib
mods = {
    "holidays": "holidays",
    "openpyxl": "openpyxl",
    "docx": "python-docx",
    "pdfplumber": "pdfplumber",
    "deep_translator": "deep-translator",
    "tkcalendar": "tkcalendar",
}
missing = []
for m, p in mods.items():
    try:
        importlib.import_module(m)
    except Exception:
        missing.append(p)
print(" ".join(missing))
PYEOF
)"

if [ -n "$MISSING" ]; then
    log "ОШИБКА: не установлены зависимости: $MISSING"
    log "Выполните: $PY -m pip install $MISSING"
    notify -u critical "База проектов" "Не установлены: $MISSING. См. logs/launch.log"
    exit 1
fi

log "Запуск: $PY ($("$PY" -V 2>&1))"

# --- 7. Старт в фоне, вывод — в лог проекта ---
nohup "$PY" "$APP_DIR/app.py" >> "$LAUNCH_LOG" 2>&1 &
PID=$!
disown "$PID" 2>/dev/null

# --- 8. Проверяем, что процесс действительно жив ---
sleep 3
if kill -0 "$PID" 2>/dev/null; then
    log "Успех: PID $PID"
    notify "База проектов" "Программа запущена (PID $PID)"
else
    ERR="$(tail -n 3 "$LAUNCH_LOG" | tr '\n' ' ')"
    log "ОШИБКА запуска: $ERR"
    notify -u critical "База проектов" "Ошибка запуска! Подробности: logs/launch.log"
    exit 1
fi