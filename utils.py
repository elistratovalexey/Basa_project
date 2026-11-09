import calendar
import os
import platform
import re
import subprocess
from datetime import datetime, timedelta
import urllib.request
import xml.etree.ElementTree as ET

# Глобальные переменные для путей (оставлены для совместимости;
# актуальные пути хранятся в модуле config)
DB_PATH = "projects.db"
CONFIG_FILE = "config.json"
LOG_FILE = "project_log.txt"


def setup_paths(db_path):
    """Устанавливает глобальные пути к файлам (совместимость, основная версия — config.setup_paths)"""
    global DB_PATH, CONFIG_FILE, LOG_FILE
    DB_PATH = db_path
    db_dir = os.path.dirname(db_path) or "."
    CONFIG_FILE = os.path.join(db_dir, "config.json")
    LOG_FILE = os.path.join(db_dir, "project_log.txt")


def add_months(source_date, months):
    if months == 0:
        return source_date
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return source_date.replace(year=year, month=month, day=day)


def add_working_days_with_holidays(start_date, days, holidays_set):
    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays_set:
            added += 1
    return current


def parse_date(date_str, fmt="%d.%m.%Y"):
    """Разбор даты ДД.ММ.ГГГГ. Возвращает datetime или None."""
    if not date_str:
        return None
    try:
        return datetime.strptime(str(date_str).strip(), fmt)
    except (ValueError, TypeError):
        return None


def get_exchange_rates():
    try:
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        response = urllib.request.urlopen(url, timeout=10)
        xml_data = response.read().decode('windows-1251')
        root = ET.fromstring(xml_data)
        rates = {'RUB': 1.0}
        for valute in root.findall('Valute'):
            char_code = valute.find('CharCode').text
            value = valute.find('Value').text.replace(',', '.')
            nominal = int(valute.find('Nominal').text)
            rate = float(value) / nominal
            rates[char_code] = rate
        return rates
    except Exception as e:
        print(f"Ошибка получения курсов: {e}")
        return {'USD': 90.0, 'EUR': 98.0, 'CNY': 12.5, 'RUB': 1.0}


_CURRENCY_TOKENS = ('₽', '€', '$', '¥', '₺', 'руб.', 'руб', 'РУБ', 'Руб', 'RUB', 'EURO', 'EUR',
                    'Евро', 'ЕВРО', 'евро', 'USD', 'CNY', 'TRY', 'TL')


def parse_number(s):
    """Разбор числа в любом привычном формате.

    Поддерживает: «1234,56», «1 234,56», «1 234,56» (неразрывный пробел),
    «1.234,56», «1,234.56», «1'234.56», «1234.56», «12 500 ₽».
    Возвращает float или None, если разобрать не удалось.
    """
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip()
    if not s:
        return None
    for token in _CURRENCY_TOKENS:
        s = s.replace(token, '')
    s = (s.replace('\xa0', '').replace('\u202f', '').replace(' ', '')
          .replace("'", '').replace('’', ''))
    if not s:
        return None
    if '.' in s and ',' in s:
        # Десятичный разделитель — тот, что стоит правее
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        # «1,234,567» — разделители тысяч, иначе запятая десятичная
        if s.count(',') > 1:
            s = s.replace(',', '')
        else:
            s = s.replace(',', '.')
    elif s.count('.') > 1:
        # «1.234.567» — разделители тысяч
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def parse_number_or_zero(s):
    """То же, что parse_number, но вместо None возвращает 0.0"""
    value = parse_number(s)
    return value if value is not None else 0.0


def format_money(value):
    """1234567.891 -> '1 234 567,89'"""
    try:
        return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return ""


def open_path(path):
    """Открывает файл или папку средствами ОС (Windows / macOS / Linux).
    Возвращает True, если команда запущена."""
    if not path or not os.path.exists(path):
        return False
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(path)  # noqa: для Windows
            return True
        if system == "Darwin":
            subprocess.Popen(["open", path])
            return True
        for cmd in (["xdg-open", path], ["libreoffice", path], ["soffice", path]):
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except FileNotFoundError:
                continue
    except Exception as e:
        print(f"Не удалось открыть {path}: {e}")
    return False


def extract_max_from_range(range_str):
    if not range_str:
        return None
    range_str = str(range_str).strip()
    match = re.match(r'(\d+)\s*[-–]\s*(\d+)', range_str)
    if match:
        return max(int(match.group(1)), int(match.group(2)))
    match = re.match(r'(\d+)', range_str)
    if match:
        return int(match.group(1))
    return None


def translate_time_unit(unit_str):
    if not unit_str:
        return "Недели"
    unit_upper = unit_str.upper().strip()
    unit_map = {
        'HAFTA': 'Недели', 'WEEK': 'Недели', 'WEEKS': 'Недели',
        'GÜN': 'Календарные дни', 'DAY': 'Календарные дни', 'DAYS': 'Календарные дни',
        'AY': 'Месяцы', 'MONTH': 'Месяцы', 'MONTHS': 'Месяцы',
        'İŞ GÜNÜ': 'Рабочие дни', 'İŞGÜNÜ': 'Рабочие дни',
        'IŞ GÜNÜ': 'Рабочие дни', 'IŞGÜNÜ': 'Рабочие дни',
        'WORKING DAYS': 'Рабочие дни', 'BUSINESS DAYS': 'Рабочие дни',
        'НЕД': 'Недели', 'НЕДЕЛЯ': 'Недели', 'НЕДЕЛИ': 'Недели', 'НЕДЕЛЬ': 'Недели',
        'ДН': 'Календарные дни', 'ДЕНЬ': 'Календарные дни', 'ДНЯ': 'Календарные дни', 'ДНЕЙ': 'Календарные дни',
        'МЕС': 'Месяцы', 'МЕСЯЦ': 'Месяцы', 'МЕСЯЦА': 'Месяцы', 'МЕСЯЦЕВ': 'Месяцы',
        'РАБ ДН': 'Рабочие дни', 'РАБОЧИХ ДНЕЙ': 'Рабочие дни', 'РАБОЧИХ ДНЯ': 'Рабочие дни',
    }
    return unit_map.get(unit_upper, "Недели")


def parse_delivery_time(time_str):
    if not time_str:
        return None, None
    time_str = str(time_str).strip()
    time_upper = time_str.upper()
    match = re.match(r'(\d+)\s*[-–]\s*(\d+)\s+([A-ZА-ЯÜŞİĞÖÇЁ]+(?:\s+[A-ZА-ЯÜŞİĞÖÇЁ]+)?)', time_upper)
    if match:
        num1 = int(match.group(1))
        num2 = int(match.group(2))
        unit = match.group(3)
        max_num = max(num1, num2)
        translated_unit = translate_time_unit(unit)
        return max_num, translated_unit
    match = re.match(r'(\d+)\s+([A-ZА-ЯÜŞİĞÖÇЁ]+(?:\s+[A-ZА-ЯÜŞİĞÖÇЁ]+)?)', time_upper)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        translated_unit = translate_time_unit(unit)
        return num, translated_unit
    return None, None
