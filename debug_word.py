#!/usr/bin/env python3
"""Диагностика парсинга Word файла"""

import sys
import os

try:
    from docx import Document
    print("✓ python-docx установлен")
except ImportError:
    print("✗ python-docx НЕ установлен!")
    print("Установите: pip install python-docx")
    sys.exit(1)

if len(sys.argv) < 2:
    print("Использование: python3 debug_word.py <файл.docx>")
    sys.exit(1)

filepath = sys.argv[1]
print(f"\nАнализ файла: {filepath}\n")

if not os.path.exists(filepath):
    print(f"✗ Файл не найден: {filepath}")
    sys.exit(1)

doc = Document(filepath)

print(f"Количество параграфов: {len(doc.paragraphs)}")
print(f"Количество таблиц: {len(doc.tables)}\n")

# Показываем первые 5 параграфов
print("=== ПЕРВЫЕ 5 ПАРАГРАФОВ ===")
for i, para in enumerate(doc.paragraphs[:5]):
    if para.text.strip():
        print(f"Параграф {i}: '{para.text[:100]}'")

# Анализируем таблицы
print("\n=== АНАЛИЗ ТАБЛИЦ ===")
for table_idx, table in enumerate(doc.tables):
    print(f"\nТаблица {table_idx}: {len(table.rows)} строк x {len(table.columns)} колонок")
    
    # Показываем первые 3 строки
    for row_idx, row in enumerate(table.rows[:3]):
        cells = []
        for cell in row.cells:
            cells.append(cell.text.strip()[:30])
        print(f"  Строка {row_idx}: {cells}")
    
    # Если таблица большая, показываем также последние 2 строки
    if len(table.rows) > 5:
        print(f"  ... (еще {len(table.rows) - 5} строк)")
        for row_idx, row in enumerate(table.rows[-2:], start=len(table.rows)-2):
            cells = []
            for cell in row.cells:
                cells.append(cell.text.strip()[:30])
            print(f"  Строка {row_idx}: {cells}")

