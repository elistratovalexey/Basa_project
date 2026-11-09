#!/bin/bash
# Скрипт запуска программы "База проектов" на Ubuntu 24.04
# с выводом информации в терминал

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Без цвета

# Устанавливаем кодировку UTF-8
export PYTHONIOENCODING=utf-8
export LANG=ru_RU.UTF-8

# Очищаем экран
clear

# Заголовок
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}    База проектов v1.7.23${NC}"
echo -e "${BLUE}    Система управления проектами${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Переходим в директорию скрипта
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo -e "${YELLOW}Рабочая директория:${NC} $PROJECT_DIR"
echo ""

# Проверяем наличие Python
echo -ne "${YELLOW}Проверка Python...${NC} "
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}ОШИБКА${NC}"
    echo -e "${RED}Python3 не установлен!${NC}"
    echo -e "Установите командой: ${YELLOW}sudo apt install python3 python3-tk python3-pip${NC}"
    echo ""
    read -p "Нажмите Enter для выхода..."
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
echo -e "${GREEN}✓${NC} $PYTHON_VERSION"

# Проверяем наличие tkinter
echo -ne "${YELLOW}Проверка tkinter...${NC} "
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo -e "${RED}ОШИБКА${NC}"
    echo -e "${RED}tkinter не установлен!${NC}"
    echo -e "Установите командой: ${YELLOW}sudo apt install python3-tk${NC}"
    echo ""
    read -p "Нажмите Enter для выхода..."
    exit 1
fi
echo -e "${GREEN}✓${NC} установлен"

# Проверяем наличие app.py
echo -ne "${YELLOW}Проверка app.py...${NC} "
if [ ! -f "app.py" ]; then
    echo -e "${RED}ОШИБКА${NC}"
    echo -e "${RED}Файл app.py не найден в директории: $PROJECT_DIR${NC}"
    echo ""
    read -p "Нажмите Enter для выхода..."
    exit 1
fi
echo -e "${GREEN}✓${NC} найден"

# Проверяем и создаем виртуальное окружение
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Виртуальное окружение не найдено. Создание...${NC}"
    python3 -m venv venv
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка создания виртуального окружения!${NC}"
        read -p "Нажмите Enter для выхода..."
        exit 1
    fi
    
    echo -e "${GREEN}✓${NC} Виртуальное окружение создано"
    echo ""
    echo -e "${YELLOW}Установка зависимостей...${NC}"
    
    source venv/bin/activate
    pip install --upgrade pip --quiet
    pip install holidays openpyxl pdfplumber deep-translator tkcalendar python-docx --quiet
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Ошибка установки зависимостей!${NC}"
        read -p "Нажмите Enter для выхода..."
        exit 1
    fi
    
    echo -e "${GREEN}✓${NC} Зависимости установлены"
    deactivate
else
    echo -e "${GREEN}✓${NC} Виртуальное окружение существует"
fi

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}    Запуск программы...${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Активируем виртуальное окружение
if [ -d "venv" ]; then
    source venv/bin/activate
    echo -e "${YELLOW}Виртуальное окружение:${NC} активно"
fi

echo ""
echo -e "${YELLOW}Дата запуска:${NC} $(date '+%d.%m.%Y %H:%M:%S')"
echo ""
echo -e "${YELLOW}Нажмите Ctrl+C для остановки программы${NC}"
echo ""

# Запуск программы с выводом всех сообщений
python3 app.py

# Сохраняем код возврата
EXIT_CODE=$?
deactivate 2>/dev/null

echo ""
echo "============================================"
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}Программа завершена успешно${NC}"
else
    echo -e "${RED}Программа завершена с ошибкой (код: $EXIT_CODE)${NC}"
    echo -e "${YELLOW}Проверьте вывод выше для диагностики${NC}"
fi
echo "============================================"
echo ""
read -p "Нажмите Enter для выхода..."
exit $EXIT_CODE