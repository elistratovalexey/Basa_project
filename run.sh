#!/bin/bash
# Скрытый запуск программы "База проектов"

cd "$(dirname "$0")"

# Активируем виртуальное окружение, если есть
if [ -d "venv" ]; then
    source venv/bin/activate
fi

export PYTHONIOENCODING=utf-8
export LANG=ru_RU.UTF-8

# Запускаем в фоне, вывод пишем в лог-файл
nohup python3 app.py > /tmp/baza_proektov.log 2>&1 &

# Показываем уведомление
notify-send "База проектов" "Программа запущена" 2>/dev/null