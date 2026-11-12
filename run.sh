#!/bin/bash
# Запуск программы "База проектов" в фоне: защита от дублей, проверка старта, лог в проекте

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$APP_DIR" || exit 1

LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"
LAUNCH_LOG="$LOG_DIR/launch.log"

log() { printf '[%s] %s\n' "$(date '+%d.%m.%Y %H:%M:%S')" "$*" >> "$LAUNCH_LOG"; }

notify() { command -v notify-send >/dev/null 2>&1 && notify-send "$@" 2>/dev/null; }

# 1. Графическая сессия обязательна (Tkinter)
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    log "ОШИБКА: нет DISPLAY — запуск из консоли без графики невозможен"
    notify -u critical "База проектов" "Нет графической сессии (DISPLAY). Запустите из рабочего стола."
    exit 1
fi

# 2. Защита от второго экземпляра
if pgrep -f "$APP_DIR/app.py" >/dev/null 2>&1; then
    log "Повторный запуск отклонён: программа уже работает"
    notify "База проектов" "Программа уже запущена"
    exit 0
fi

# 3. Явный выбор интерпретатора (venv важнее системного)
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

# 4. Кодировка и локаль (с фолбэком, если ru_RU не сгенерирована)
export PYTHONIOENCODING=utf-8
if locale -a 2>/dev/null | grep -qiE '^ru_RU\.(utf8|UTF-8)$'; then
    export LANG=ru_RU.UTF-8
else
    export LANG=C.UTF-8
fi

# 5. Проверка наличия приложения
if [ ! -f "$APP_DIR/app.py" ]; then
    log "ОШИБКА: не найден $APP_DIR/app.py"
    notify -u critical "База проектов" "Файл app.py не найден"
    exit 1
fi

log "Запуск: $PY ($("$PY" -V 2>&1))"

# 6. Старт в фоне, вывод — в лог проекта
nohup "$PY" "$APP_DIR/app.py" >> "$LAUNCH_LOG" 2>&1 &
PID=$!
disown "$PID" 2>/dev/null

# 7. Проверяем, что процесс действительно жив
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