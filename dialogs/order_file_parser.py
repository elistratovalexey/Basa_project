import os
import re

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

try:
    import camelot
    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False


# =================================================================
# PRE-PROCESS: склейка физических продолжений
# =================================================================
def _join_continuation_lines(lines):
    """Склеивает физические строки-продолжения.
    Строка считается продолжением, если она НЕ начинается с '|'
    и НЕ является строкой-разделителем. Чинит разрывы вида:
        | ITEM|DESCRIPTION|QTY|Unıt Price
        (EURO)|Total Price
        (EURO)|
    """
    out = []
    for raw in lines:
        s = raw.rstrip()
        if not s.strip():
            out.append(s)
            continue
        if out and not s.lstrip().startswith('|') \
                and not re.match(r'^\s*[-=\s]+$', s):
            out[-1] = out[-1] + ' ' + s.strip()
        else:
            out.append(s)
    return out


# =================================================================
# Вспомогательные функции международного парсера
# =================================================================
def _clean_intl_number(s):
    """Универсальная очистка числа: ￥4,875.00 (US) и 1.337,40 (EU) -> float."""
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r'[€$￥£₺]\s*', '', s)
    s = s.replace(' ', '').replace('\xa0', '')
    if not s:
        return None
    last_comma = s.rfind(',')
    last_dot = s.rfind('.')
    if last_comma >= 0 and last_dot >= 0:
        if last_comma > last_dot:      # 1.337,40 → точка=тысячи
            s = s.replace('.', '').replace(',', '.')
        else:                          # 4,875.00 → запятая=тысячи
            s = s.replace(',', '')
    elif last_comma >= 0:
        dec = s[last_comma + 1:]
        s = s.replace(',', '.') if 1 <= len(dec) <= 2 else s.replace(',', '')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def _detect_currency(blob):
    """Определяет валюту по тексту (заголовок + следующие строки)."""
    up = blob.upper()
    if 'CNY' in up or '￥' in blob or 'YUAN' in up:
        return 'CNY'
    if 'EURO' in up or 'EUR' in up or '€' in blob:
        return 'EUR'
    if 'USD' in up or '$' in blob:
        return 'USD'
    if 'TRY' in up or '₺' in blob:
        return 'TRY'
    return 'RUB'


def _map_intl_header(cells_up):
    """Определяет индексы колонок в pipe-заголовке."""
    idx = {'item': -1, 'desc': -1, 'qty': -1,
           'price': -1, 'total': -1, 'lead': -1, 'note': -1, 'mfr': -1}
    for i, c in enumerate(cells_up):
        cu = c.upper()
        if idx['mfr'] < 0 and 'MANUFACTURER' in cu:
            idx['mfr'] = i
        elif idx['item'] < 0 and ('ITEM' in cu or 'ARTICLE' in cu or 'PART' in cu):
            idx['item'] = i
        elif idx['desc'] < 0 and ('DESCRIPTION' in cu or 'NAME' in cu):
            idx['desc'] = i
        elif idx['qty'] < 0 and ('QTY' in cu or 'QUANTITY' in cu):
            idx['qty'] = i
        elif idx['lead'] < 0 and ('LEAD' in cu or 'DELIVERY' in cu):
            idx['lead'] = i
        elif idx['note'] < 0 and ('NOTE' in cu or 'REMARK' in cu):
            idx['note'] = i
    joined = ' '.join(cells_up)
    m_total = re.search(r'\bTOTAL\s*PRICE\b', joined)
    m_price = re.search(r'\bUNIT\s*PRICE\b|\bPRICE\b', joined)
    if m_total:
        pos = m_total.start()
        cursor = 0
        for i, c in enumerate(cells_up):
            if cursor <= pos < cursor + len(c):
                idx['total'] = i
                break
            cursor += len(c) + 1
    if m_price:
        pos = m_price.start()
        cursor = 0
        for i, c in enumerate(cells_up):
            if cursor <= pos < cursor + len(c):
                idx['price'] = i
                break
            cursor += len(c) + 1
    if idx['price'] < 0:
        for i, c in enumerate(cells_up):
            if 'PRICE' in c and 'TOTAL' not in c:
                idx['price'] = i
                break
    if idx['total'] < 0:
        for i, c in enumerate(cells_up):
            if 'TOTAL' in c:
                idx['total'] = i
                break
    return idx


# =================================================================
# РЕЖИМ B: pipe-строки (целая строка таблицы = одна физическая строка)
# =================================================================
def _parse_intl_pipe_rows(lines):
    """Режим: pipe-строки (с '|' в качестве разделителя ячеек)."""
    colmap = None
    currency = 'RUB'
    rows = []
    n_cols_expected = 0
    for line in lines:
        s = line.strip()
        if s.count('|') < 3:
            continue
        cells = [c.strip() for c in s.split('|')]
        while cells and cells[0] == '':
            cells.pop(0)
        while cells and cells[-1] == '':
            cells.pop()
        if not cells:
            continue
        if all(re.fullmatch(r'[\-:\s]*', c or '') for c in cells):
            continue
        up = [c.upper() for c in cells]
        joined = ' '.join(up)
        if colmap is None:
            if ('ITEM' in joined or 'ARTICLE' in joined or 'DESCRIPTION' in joined) and \
               ('QTY' in joined or 'QUANTITY' in joined) and \
               ('PRICE' in joined or 'TOTAL' in joined):
                colmap = _map_intl_header(up)
                currency = _detect_currency(joined)
                n_cols_expected = len(cells)
                print(f"[INTL-PIPE] Заголовок: {cells} валюта={currency} colmap={colmap}")
            continue
        if 'TOTAL AMOUNT' in joined or 'GRAND TOTAL' in joined or joined.startswith('TOTAL'):
            continue
        if len(cells) < max(3, n_cols_expected - 2):
            continue

        def g(k):
            j = colmap.get(k, -1)
            return cells[j] if 0 <= j < len(cells) else ''

        article = g('item')
        name = g('desc') or article
        if not article and not name:
            continue
        qty_v = _clean_intl_number(g('qty'))
        price_v = _clean_intl_number(g('price'))
        total_v = _clean_intl_number(g('total'))
        if qty_v is None or qty_v <= 0 or (price_v is None and total_v is None):
            continue
        if total_v is None:
            total_v = qty_v * price_v
        if price_v is None:
            price_v = total_v / qty_v
        qty_str = str(int(qty_v)) if qty_v == int(qty_v) else f"{qty_v:.3f}".rstrip('0').rstrip('.')
        rows.append([
            str(len(rows) + 1), article, name, qty_str, 'шт.',
            f"{price_v:.2f}", f"{total_v:.2f}", g('lead'), g('mfr'), g('note'), currency,
        ])
        print(f"[INTL-PIPE] ✓ {article} qty={qty_str} price={rows[-1][5]} total={rows[-1][6]}")
    print(f"[INTL-PIPE] найдено {len(rows)} строк")
    return rows


# =================================================================
# РЕЖИМ C: pipe-ячейки (каждая ячейка на отдельной строке '|...')
# =================================================================
def _parse_intl_pipe_cells(lines):
    """Режим C: каждая ячейка на отдельной строке '|...'
    (типично для турецких PROFORMA INVOICE ARKKONTROL)."""
    header = []
    data_rows = []
    cur_row = []
    stage = 'header'

    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if not s.startswith('|'):
            if cur_row:
                data_rows.append(cur_row)
                cur_row = []
            break
        cell = s.strip('| ').strip()
        if re.fullmatch(r'[\-:\s|]+', s):
            if stage == 'header' and header:
                stage = 'data'
            continue
        if stage == 'header':
            if header and cell.startswith('('):
                header[-1] = (header[-1] + ' ' + cell).strip()
            else:
                header.append(cell)
            continue
        if stage == 'data':
            cur_row.append(cell)
            if len(cur_row) == len(header):
                data_rows.append(cur_row)
                cur_row = []
    if cur_row and len(cur_row) == len(header):
        data_rows.append(cur_row)

    if len(header) < 3 or not data_rows:
        return []

    colmap = _map_intl_header([h.upper() for h in header])
    head_up = ' '.join(header).upper()
    currency = _detect_currency(head_up)
    print(f"[INTL-CELL] Заголовок ({len(header)} колонок): {header}")
    print(f"[INTL-CELL] colmap={colmap} валюта={currency} строк данных={len(data_rows)}")

    rows = []
    for n, cells in enumerate(data_rows, start=1):
        def g(k):
            j = colmap.get(k, -1)
            return cells[j].strip() if 0 <= j < len(cells) else ''
        article = g('item')
        name = g('desc') or article
        if not article and not name:
            continue
        qty_raw = g('qty')
        m_qty = re.search(r'[\d.,]+', qty_raw)
        qty_v = _clean_intl_number(m_qty.group(0) if m_qty else qty_raw)
        price_v = _clean_intl_number(g('price'))
        total_v = _clean_intl_number(g('total'))
        if qty_v is None or qty_v <= 0 or (price_v is None and total_v is None):
            continue
        if total_v is None:
            total_v = qty_v * price_v
        if price_v is None:
            price_v = total_v / qty_v
        qty_str = str(int(qty_v)) if qty_v == int(qty_v) else f"{qty_v:.3f}".rstrip('0').rstrip('.')
        rows.append([
            str(len(rows) + 1), article, name, qty_str, 'шт.',
            f"{price_v:.2f}", f"{total_v:.2f}", g('lead'), g('mfr'), g('note'), currency,
        ])
        print(f"[INTL-CELL] ✓ {article} qty={qty_str} price={rows[-1][5]} total={rows[-1][6]}")
    print(f"[INTL-CELL] найдено {len(rows)} строк")
    return rows


# =================================================================
# ГЛАВНАЯ ФУНКЦИЯ МЕЖДУНАРОДНОГО ПАРСЕРА
# =================================================================
def parse_international_quote_from_text(text):
    """Парсинг международных КП: Siemens (CNY), ARKKONTROL (EUR) и т.п.
    ВАЖНО: без сплошной склейки строк — раньше _join_continuation_lines
    схлопывал весь документ без '|' в одну строку, и парсер видел
    «заголовок» в начале файла и ноль строк данных."""
    lines = text.split('\n')

    # === Режим B: pipe-строки (вся строка таблицы на одной линии с '|') ===
    pipe_lines = [l for l in lines if l.strip().count('|') >= 3]
    if len(pipe_lines) >= 3:
        rows = _parse_intl_pipe_rows(lines)
        if rows:
            return rows

    # === Режим C: pipe-ячейки (каждая ячейка на отдельной строке '|...') ===
    pipe_cell_lines = [l for l in lines if l.strip().startswith('|') and l.strip().count('|') <= 2]
    if len(pipe_cell_lines) >= 6:
        rows = _parse_intl_pipe_cells(lines)
        if rows:
            return rows

    # === Режим A: пробельные токены + буфер перенесённых строк ===
    rows = []
    header_found = False
    currency = 'RUB'
    last_row = None
    pending = ''

    # Siemens-стиль: Производитель Артикул Кол-во Цена Сумма [срок/примечание]
    row_re = re.compile(
        r'^(?P<mfr>\S+)\s+(?P<art>[A-Za-z0-9][A-Za-z0-9\-\/_\.]*)\s+(?P<qty>\d+)\s+'
        r'(?P<price>[￥$€£₺]?\s?\d[\d.,]*[.,]\d{2})\s+(?P<total>[￥$€£₺]?\s?\d[\d.,]*[.,]\d{2})\s*(?P<rest>.*)$'
    )
    # ARKKONTROL-стиль: Артикул(с запятыми) Описание Кол-во [ед.] Цена Сумма
    row_re_eu = re.compile(
        r'^(?P<art>[A-Za-z0-9][A-Za-z0-9\-\/_\.]*(?:,[A-Za-z0-9\-\/_\.]+)*)\s+'
        r'(?P<desc>.+?)\s+'
        r'(?P<qty>\d{1,5})\s+'
        r'(?:[A-Za-zА-Яа-яİıŞşÖöÇçĞğÜü]{1,12}\.?\s+)?'
        r'(?P<price>[￥$€£₺]?\d[\d.,]*[.,]\d{2})\s+'
        r'(?P<total>[￥$€£₺]?\d[\d.,]*[.,]\d{2})\s*$'
    )
    price_shape = re.compile(r'^[￥$€£₺]?\d[\d.,]*[.,]\d{2}$')
    art_shape = re.compile(
        r'^[A-Za-z0-9][A-Za-z0-9\-\/_\.]*(?:,[A-Za-z0-9\-\/_\.]+)+$'
        r'|^(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-\/_\.]{5,}$')

    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        i += 1
        if not s:
            continue
        up = s.upper()

        # Заголовок ищем СТРОГО: ITEM/ARTICLE/MANUFACTURER + QTY/QUANTITY + PRICE/TOTAL.
        # Валюта — из строки заголовка и двух следующих (там бывает "(EURO)").
        if not header_found:
            window = up + ' ' + (lines[i].strip().upper() if i < n else '')
            if ('ARTICLE' in window or 'MANUFACTURER' in window or 'ITEM' in window) and \
               ('QTY' in window or 'QUANTITY' in window) and ('PRICE' in window or 'TOTAL' in window):
                header_found = True
                blob = ' '.join([up] + [lines[j].strip().upper() for j in range(i, min(i + 2, n))])
                currency = _detect_currency(blob)
                print(f"[INTL] Найден заголовок КП: '{s[:80]}' валюта={currency}")
            continue

        if any(k in up for k in ['TOTAL AMOUNT', 'GRAND TOTAL', 'ИТОГО', 'ВСЕГО:']):
            pending = ''
            continue
        if up.startswith(('DELIVERY', 'PAYMENT', 'VALIDITY', 'E-MAIL', 'EMAIL', 'CONTACT',
                          'THE ACCOUNT', 'NAME/BRANCH', 'SWIFT CODE', 'IBAN')):
            last_row = None
            pending = ''
            continue
        if re.fullmatch(r'\d{1,2}', s):
            continue

        s2 = re.sub(r'\s+', ' ', s.replace('|', ' ')).strip()
        # НОВОЕ: убираем хвостовой символ валюты: "3.810,56 €" -> "3.810,56"
        s2 = re.sub(r'(\d)\s*[€￥$£₺]', r'\1', s2)
        tokens = s2.split()
        has_price = any(price_shape.match(t) for t in tokens)

        cand = (pending + ' ' + s2).strip() if pending else s2

        m = row_re.match(cand)
        m2 = None if m else row_re_eu.match(cand)
        if m or m2:
            if m:
                rest = m.group('rest').strip()
                lead = ''
                note = ''
                lm = re.search(r'\d+\s*[-–]\s*\d+\s*(weeks?|days?|мес|нед|дн)', rest, re.I) or \
                     re.search(r'\d+\s*(weeks?|days?)', rest, re.I)
                if lm:
                    lead = lm.group(0)
                    note = (rest[:lm.start()] + ' ' + rest[lm.end():]).strip()
                else:
                    note = rest
                price_v = _clean_intl_number(m.group('price'))
                total_v = _clean_intl_number(m.group('total'))
                if price_v is None or total_v is None:
                    pending = ''
                    continue
                last_row = [
                    str(len(rows) + 1), m.group('art'), m.group('art'), m.group('qty'), 'шт.',
                    f"{price_v:.2f}", f"{total_v:.2f}", lead, m.group('mfr'), note, currency,
                ]
            else:
                price_v = _clean_intl_number(m2.group('price'))
                total_v = _clean_intl_number(m2.group('total'))
                qty_v = _clean_intl_number(m2.group('qty'))
                if price_v is None or total_v is None or not qty_v:
                    pending = ''
                    continue
                qty_str = str(int(qty_v)) if qty_v == int(qty_v) else f"{qty_v:.3f}".rstrip('0').rstrip('.')
                last_row = [
                    str(len(rows) + 1), m2.group('art'), m2.group('desc'), qty_str, 'шт.',
                    f"{price_v:.2f}", f"{total_v:.2f}", '', '', '', currency,
                ]
            rows.append(last_row)
            pending = ''
            print(f"[INTL] ✓ Строка {len(rows)}: {last_row[1]} qty={last_row[3]} "
                  f"price={last_row[5]} total={last_row[6]}")
            continue

        # Совпадения нет: начало перенесённой строки товара ИЛИ продолжение примечания
        if pending:
            pending = (pending + ' ' + s2).strip()
            if len(pending) > 600:
                pending = ''
            continue
        if tokens and art_shape.match(tokens[0]):
            pending = s2
            print(f"[INTL] буферизация переноса: '{s2[:60]}...'")
            continue
        if last_row is not None and not has_price:
            last_row[9] = (last_row[9] + ' ' + s2).strip()
            continue

    print(f"[INTL] ЗАВЕРШЁН: найдено {len(rows)} строк")
    return rows

# =================================================================
# ОСНОВНАЯ ТОЧКА ВХОДА
# =================================================================
def parse_file_to_rows_with_text(filepath):
    """Парсинг Excel, PDF и Word файлов"""
    rows = []
    full_text = ""
    ext = os.path.splitext(filepath)[1].lower()

    if ext in ['.xlsx', '.xls']:
        if not HAS_OPENPYXL:
            raise ImportError("Установите: pip install openpyxl")
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if row and any(cell is not None for cell in row):
                rows.append([str(cell).strip() if cell is not None else "" for cell in row])
                full_text += " ".join(str(cell) for cell in row if cell) + "\n"

    elif ext == '.docx':
        if not HAS_DOCX:
            raise ImportError("Установите: pip install python-docx")

        print(f"Парсинг Word файла: {filepath}")
        doc = Document(filepath)

        tables_data = []
        for table_num, table in enumerate(doc.tables):
            table_data = []
            for row in table.rows:
                row_data = [cell.text.strip() if cell.text else "" for cell in row.cells]
                if row_data:
                    table_data.append(row_data)
            if table_data:
                tables_data.append(table_data)
                print(f"Таблица {table_num}: {len(table_data)} строк x {len(table_data[0])} колонок")
                if table_data:
                    print(f"  Заголовки: {table_data[0]}")

        items_table = None
        best_score = 0

        for table in tables_data:
            if not table or len(table) < 2:
                continue

            header_text = ' '.join([str(c).upper() for c in table[0]])
            print(f"Анализ заголовков: {header_text}")

            keywords = ['ТОВАР', 'НАИМЕН', 'КОЛИЧЕСТВО', 'ЦЕНА', 'СУММ', 'АРТИКУЛ',
                       'ОПИСАНИЕ', 'НАИМЕНОВАНИЕ', 'НОМЕР', 'ЕД.', 'КОЛ-ВО',
                       'ARTICLE', 'PRODUCT', 'DESCRIPTION', 'NAME', 'QUANTITY', 'QTY',
                       'PRICE', 'TOTAL', 'UNIT PRICE', 'DELIVERY', '№', 'NO.', 'SIRA']

            score = sum(1 for word in keywords if word in header_text)
            print(f"  Score: {score}")

            if score > best_score:
                best_score = score
                items_table = table

        if not items_table and tables_data:
            items_table = max(tables_data, key=len)

        if items_table:
            print(f"\nНайдена таблица Word с {len(items_table)} строками")
            print(f"Заголовки: {items_table[0]}")

            col_indices = {
                'number': -1, 'article': -1, 'name': -1,
                'quantity': -1, 'unit': -1, 'price': -1, 'total': -1,
                'currency': 'RUB'
            }

            header = items_table[0]
            quantity_found = False

            for i, cell in enumerate(header):
                if not cell:
                    continue
                cell_upper = str(cell).upper().strip()
                print(f"  Колонка {i}: '{cell}' -> '{cell_upper}'")

                if cell_upper in ['№', 'N', 'NUM', 'НОМЕР', 'SIRA', 'NO.', 'NO', 'NUM.', '№П/П']:
                    col_indices['number'] = i
                elif any(word in cell_upper for word in ['АРТИКУЛ', 'ARTICLE', 'КОД', 'CODE', 'REFERANS', 'KOD', 'PARTNO', 'ITEM', 'MODEL', 'CATALOG']):
                    col_indices['article'] = i
                elif any(word in cell_upper for word in ['НАИМЕН', 'ТОВАР', 'DESCRIPTION', 'ОПИСАНИЕ', 'NAME', 'PRODUCT', 'ITEM', 'ТОВАРЫ', 'УСЛУГА']):
                    col_indices['name'] = i
                elif any(word in cell_upper for word in ['КОЛИЧ', 'QUANT', 'QTY', 'КОЛ-ВО', 'ADET', 'MIKTAR', 'QUANTITY']):
                    if not quantity_found:
                        col_indices['quantity'] = i
                        quantity_found = True
                        print(f"    -> Количество (число)")
                    else:
                        col_indices['unit'] = i
                        print(f"    -> Единица измерения")
                elif cell_upper in ['ЕД', 'ЕД.', 'UNIT', 'ШТ', 'ШТ.', 'BİRİM', 'BIRIM', 'ADET']:
                    col_indices['unit'] = i
                elif any(word in cell_upper for word in ['ЦЕНА', 'PRICE', 'FİYAT', 'FIYAT', 'СТОИМ', 'UNITPRICE']) \
                        and 'TOTAL' not in cell_upper \
                        and 'СУММ' not in cell_upper:
                    col_indices['price'] = i
                    if 'ЕВРО' in cell_upper or 'EURO' in cell_upper or 'EUR' in cell_upper:
                        col_indices['currency'] = 'EUR'
                        print(f"    -> Валюта: EUR")
                    elif 'РУБ' in cell_upper or 'RUB' in cell_upper or '₽' in cell_upper:
                        col_indices['currency'] = 'RUB'
                        print(f"    -> Валюта: RUB")
                    elif 'ДОЛЛ' in cell_upper or 'USD' in cell_upper or '$' in cell_upper:
                        col_indices['currency'] = 'USD'
                        print(f"    -> Валюта: USD")
                    elif 'ЮАНЬ' in cell_upper or 'CNY' in cell_upper or '¥' in cell_upper:
                        col_indices['currency'] = 'CNY'
                        print(f"    -> Валюта: CNY")
                    elif 'ЛИРА' in cell_upper or 'TRY' in cell_upper or '₺' in cell_upper:
                        col_indices['currency'] = 'TRY'
                        print(f"    -> Валюта: TRY")
                elif any(word in cell_upper for word in ['СУММ', 'TOTAL', 'ИТОГО', 'TOPLAM', 'AMOUNT', 'SUM', 'СНДС']):
                    col_indices['total'] = i
                elif any(word in cell_upper for word in ['СРОК', 'DELIVERY', 'ПОСТАВК', 'TESLİM', 'TESLIM', 'LEAD']):
                    col_indices['delivery'] = i

            print(f"\nИтоговые индексы колонок: {col_indices}")

            if col_indices['name'] == -1 and len(items_table) > 1:
                sample_row = items_table[1]
                max_len = 0
                for i, cell in enumerate(sample_row):
                    if cell and len(str(cell)) > max_len:
                        try:
                            float(str(cell).replace(',', '.').replace(' ', ''))
                        except:
                            max_len = len(str(cell))
                            col_indices['name'] = i

            for row_idx, row in enumerate(items_table[1:], start=2):
                if not row:
                    continue

                row_text = ' '.join([str(c) for c in row if c]).upper()
                print(f"Строка {row_idx}: {row_text[:100]}")

                if any(word in row_text for word in ['ИТОГО', 'TOTAL:', 'TOTAL AMOUNT', 'GRAND TOTAL', 'SUBTOTAL', 'ОБЩАЯ СУММА', 'НДС']):
                    print(f"  Пропускаем служебную строку")
                    continue

                normalized_row = [''] * 11
                normalized_row[10] = col_indices['currency']

                if col_indices['number'] >= 0 and col_indices['number'] < len(row):
                    normalized_row[0] = str(row[col_indices['number']]).strip() if row[col_indices['number']] else ''
                if not normalized_row[0]:
                    normalized_row[0] = str(len(rows) + 1)
                if col_indices['article'] >= 0 and col_indices['article'] < len(row):
                    normalized_row[1] = str(row[col_indices['article']]).strip() if row[col_indices['article']] else ''
                if col_indices['name'] >= 0 and col_indices['name'] < len(row):
                    normalized_row[2] = str(row[col_indices['name']]).strip() if row[col_indices['name']] else ''
                if col_indices['quantity'] >= 0 and col_indices['quantity'] < len(row):
                    normalized_row[3] = str(row[col_indices['quantity']]).strip() if row[col_indices['quantity']] else ''
                if col_indices['unit'] >= 0 and col_indices['unit'] < len(row):
                    normalized_row[4] = str(row[col_indices['unit']]).strip() if row[col_indices['unit']] else ''
                if col_indices['price'] >= 0 and col_indices['price'] < len(row):
                    normalized_row[5] = str(row[col_indices['price']]).strip() if row[col_indices['price']] else ''
                if col_indices['total'] >= 0 and col_indices['total'] < len(row):
                    normalized_row[6] = str(row[col_indices['total']]).strip() if row[col_indices['total']] else ''
                # НОВОЕ: нормализация чисел к точечному формату (см. PDF-ветку)
                for idx in (3, 5, 6):
                    raw_v = normalized_row[idx]
                    if raw_v:
                        fv = _clean_intl_number(str(raw_v))
                        if fv is not None:
                            if idx == 3:
                                normalized_row[idx] = str(int(fv)) if fv == int(fv) \
                                    else f"{fv:.3f}".rstrip('0').rstrip('.')
                            else:
                                normalized_row[idx] = f"{fv:.2f}"

                name = normalized_row[2]
                has_numbers = False
                for idx in [3, 5, 6]:
                    if normalized_row[idx]:
                        try:
                            val = float(str(normalized_row[idx]).replace(',', '.').replace(' ', ''))
                            if val > 0:
                                has_numbers = True
                                break
                        except:
                            pass

                if name or has_numbers:
                    rows.append(normalized_row)
                    print(f"  ✓ Добавлена строка {len(rows)}: {name[:50]}...")

        for para in doc.paragraphs:
            if para.text.strip():
                full_text += para.text + "\n"

    elif ext == '.pdf':
        try:
            import pdfplumber
        except ImportError:
            raise ImportError("Установите: pip install pdfplumber")

        print("Попытка извлечения текста из PDF...")
        text_pdfplumber = ""
        tables_pdfplumber = []

        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_pdfplumber += page_text + "\n"
                    tables = page.extract_tables()
                    if tables:
                        tables_pdfplumber.extend(tables)
        except Exception as e:
            print(f"Ошибка при извлечении текста pdfplumber: {e}")

        has_text_layer = bool(text_pdfplumber.strip())
        if has_text_layer:
            print("✓ PDF содержит текстовый слой")
            full_text = text_pdfplumber

            items_table = None
            best_score = 0

            for table in tables_pdfplumber:
                if not table or len(table) < 2:
                    continue

                header_text = ' '.join([str(c).upper() for c in table[0] if c])
                print(f"Анализ заголовков: {header_text[:100]}...")

                keywords = ['ТОВАР', 'НАИМЕН', 'КОЛИЧЕСТВО', 'ЦЕНА', 'СУММ', 'КОД',
                           'АРТИКУЛ', 'ОПИСАНИЕ', 'ЕД.', 'НДС', 'СТАТУС', 'СРОК',
                           'ITEM', 'DESCRIPTION', 'QTY', 'QUANTITY', 'PRICE', 'TOTAL',
                           'MANUFACTURER', 'ARTICLE', 'UNIT', 'LEAD']

                score = sum(1 for word in keywords if word in header_text)
                print(f"  Score: {score}")

                if score > best_score:
                    best_score = score
                    items_table = table

            if items_table and len(items_table) > 1:
                print(f"Найдена таблица с {len(items_table)} строками")
                header = items_table[0]
                print(f"Заголовки: {header}")

                col_indices = {
                    'number': -1, 'code': -1, 'name': -1, 'status': -1,
                    'delivery_term': -1, 'quantity': -1, 'unit': -1,
                    'price_no_vat': -1, 'vat_amount': -1, 'price_with_vat': -1,
                    'total_no_vat': -1, 'total_with_vat': -1,
                    'currency': 'RUB'
                }

                for i, cell in enumerate(header):
                    if not cell:
                        continue
                    cell_upper = str(cell).upper().strip().replace('\n', '')

                    if cell_upper in ['№', 'N', 'NUM', 'НОМЕР']:
                        col_indices['number'] = i
                    elif any(word in cell_upper for word in ['КОД', 'CODE', 'ARTICLE', 'ID', 'ITEM']):
                        col_indices['code'] = i
                    elif any(word in cell_upper for word in ['ТОВАР', 'НАИМЕН', 'DESCRIPTION', 'ОПИСАНИЕ', 'NAME', 'PRODUCT']):
                        col_indices['name'] = i
                    elif 'СТАТУС' in cell_upper or 'STATUS' in cell_upper:
                        col_indices['status'] = i
                    elif any(word in cell_upper for word in ['СРОК', 'DELIVERY', 'ПОСТАВК', 'LEAD']):
                        col_indices['delivery_term'] = i
                    elif any(word in cell_upper for word in ['КОЛИЧ', 'QUANT', 'QTY', 'КОЛ-ВО']):
                        col_indices['quantity'] = i
                    elif cell_upper in ['ЕД', 'ЕД.', 'UNIT', 'ШТ', 'BİRİM']:
                        col_indices['unit'] = i
                    elif any(word in cell_upper for word in ['ЦЕНА БЕЗ НДС', 'PRICE NO VAT', 'BASE PRICE']):
                        col_indices['price_no_vat'] = i
                    elif 'НДС' in cell_upper and 'СУММА' not in cell_upper:
                        col_indices['vat_amount'] = i
                    elif any(word in cell_upper for word in ['ЦЕНА', 'PRICE', 'FİYAT']) \
                            and 'БЕЗ' not in cell_upper \
                            and 'TOTAL' not in cell_upper \
                            and 'СУММА' not in cell_upper:
                        col_indices['price_with_vat'] = i
                        if 'EURO' in cell_upper or 'EUR' in cell_upper or '€' in cell_upper:
                            col_indices['currency'] = 'EUR'
                        elif 'CNY' in cell_upper or '￥' in cell_upper or 'YUAN' in cell_upper:
                            col_indices['currency'] = 'CNY'
                        elif 'USD' in cell_upper or '$' in cell_upper:
                            col_indices['currency'] = 'USD'
                    elif any(word in cell_upper for word in ['СУММА БЕЗ НДС', 'TOTAL NO VAT', 'SUBTOTAL']):
                        col_indices['total_no_vat'] = i
                    elif any(word in cell_upper for word in ['СУММА', 'TOTAL', 'ИТОГО', 'AMOUNT', 'SUM']) and 'БЕЗ' not in cell_upper:
                        col_indices['total_with_vat'] = i
                        if 'EURO' in cell_upper or 'EUR' in cell_upper or '€' in cell_upper:
                            col_indices['currency'] = 'EUR'
                        elif 'CNY' in cell_upper or '￥' in cell_upper or 'YUAN' in cell_upper:
                            col_indices['currency'] = 'CNY'
                        elif 'USD' in cell_upper or '$' in cell_upper:
                            col_indices['currency'] = 'USD'

                if col_indices['price_with_vat'] == -1 and col_indices['price_no_vat'] != -1 and col_indices['vat_amount'] != -1:
                    col_indices['price_with_vat'] = col_indices['price_no_vat']

                print(f"Индексы колонок: {col_indices}")

                for row_idx, row in enumerate(items_table[1:], start=2):
                    if not row:
                        continue

                    row_text = ' '.join([str(c) for c in row if c]).upper()
                    print(f"Строка {row_idx}: {row_text[:80]}...")

                    if any(word in row_text for word in ['ИТОГО', 'ВСЕГО', 'НДС', 'НАИМЕНОВАНИЙ',
                                                          'ОБЩАЯ СУММА', 'ВСЕГО К ОПЛАТЕ',
                                                          'TOTAL AMOUNT', 'GRAND TOTAL', 'SUBTOTAL']):
                        print(f"  Пропускаем служебную строку")
                        continue

                    normalized_row = [''] * 11
                    normalized_row[10] = col_indices['currency']

                    if col_indices['number'] >= 0 and col_indices['number'] < len(row):
                        normalized_row[0] = str(row[col_indices['number']]).strip() if row[col_indices['number']] else ''
                    # НОВОЕ: если колонки "№" в документе нет (ARKKONTROL, Siemens),
                    # нумеруем последовательно — FileImportMatchDialog не принимает
                    # строки файла с пустым номером
                    if not normalized_row[0]:
                        normalized_row[0] = str(len(rows) + 1)
                    if col_indices['code'] >= 0 and col_indices['code'] < len(row):
                        normalized_row[1] = str(row[col_indices['code']]).strip() if row[col_indices['code']] else ''
                    if col_indices['name'] >= 0 and col_indices['name'] < len(row):
                        normalized_row[2] = str(row[col_indices['name']]).strip() if row[col_indices['name']] else ''
                    if col_indices['quantity'] >= 0 and col_indices['quantity'] < len(row):
                        normalized_row[3] = str(row[col_indices['quantity']]).strip() if row[col_indices['quantity']] else ''
                    if col_indices['unit'] >= 0 and col_indices['unit'] < len(row):
                        normalized_row[4] = str(row[col_indices['unit']]).strip() if row[col_indices['unit']] else ''

                    price_source = col_indices['price_with_vat'] if col_indices['price_with_vat'] != -1 else col_indices['price_no_vat']
                    if price_source >= 0 and price_source < len(row):
                        normalized_row[5] = str(row[price_source]).strip() if row[price_source] else ''

                    total_source = col_indices['total_with_vat'] if col_indices['total_with_vat'] != -1 else col_indices['total_no_vat']
                    if total_source >= 0 and total_source < len(row):
                        normalized_row[6] = str(row[total_source]).strip() if row[total_source] else ''

                    if col_indices['delivery_term'] >= 0 and col_indices['delivery_term'] < len(row):
                        normalized_row[7] = str(row[col_indices['delivery_term']]).strip() if row[col_indices['delivery_term']] else ''
                    # НОВОЕ: приводим кол-во/цену/сумму к точечному формату.
                    # FileImportMatchDialog парсит цену через float() и пропускает
                    # строки вида '64,51' — поэтому нормализуем здесь.
                    for idx in (3, 5, 6):
                        raw_v = normalized_row[idx]
                        if raw_v:
                            fv = _clean_intl_number(str(raw_v))
                            if fv is not None:
                                if idx == 3:
                                    normalized_row[idx] = str(int(fv)) if fv == int(fv) \
                                        else f"{fv:.3f}".rstrip('0').rstrip('.')
                                else:
                                    normalized_row[idx] = f"{fv:.2f}"

                    name = normalized_row[2]
                    has_numbers = False
                    for idx in [3, 5, 6]:
                        if normalized_row[idx]:
                            try:
                                val = float(str(normalized_row[idx]).replace(',', '.').replace(' ', '').replace('₽', '').replace('руб', ''))
                                if val > 0:
                                    has_numbers = True
                                    break
                            except:
                                pass

                    if name or (has_numbers and normalized_row[3]):
                        rows.append(normalized_row)
                        print(f"  ✓ Добавлена строка {len(rows)}: {name[:40]}...")

            if not rows and full_text:
                print("Таблицы не найдены через extract_tables(), пробуем парсинг текста...")
                rows = parse_invoice_from_text(full_text)
            # Международные КП (Siemens CNY, ARKKONTROL EUR и т.п.)
            if not rows and full_text:
                rows = parse_international_quote_from_text(full_text)
        else:
            print("PDF не содержит текстовый слой (сканированный)")
            if HAS_CAMELOT:
                try:
                    tables_lattice = camelot.read_pdf(filepath, pages='all', flavor='lattice')
                    if tables_lattice:
                        for table in tables_lattice:
                            df = table.df
                            for _, row in df.iterrows():
                                rows.append(row.tolist())
                            full_text += df.to_string() + "\n"
                    else:
                        tables_stream = camelot.read_pdf(filepath, pages='all', flavor='stream')
                        if tables_stream:
                            for table in tables_stream:
                                df = table.df
                                for _, row in df.iterrows():
                                    rows.append(row.tolist())
                                full_text += df.to_string() + "\n"
                except Exception as e:
                    print(f"Ошибка Camelot: {e}")

            if not full_text.strip() and HAS_OCR:
                try:
                    images = convert_from_path(filepath, dpi=300)
                    for i, image in enumerate(images):
                        text = pytesseract.image_to_string(image, lang='rus+eng')
                        if text.strip():
                            full_text += f"\n=== Страница {i+1} ===\n{text}\n"
                except Exception as e:
                    print(f"Ошибка OCR: {e}")

        # Международные КП до общего табличного fallback'а
        if not rows and full_text:
            rows = parse_international_quote_from_text(full_text)
        if not rows and full_text:
            rows = parse_table_from_text(full_text)
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}. Поддерживаются Word (.docx), Excel (.xlsx, .xls) и PDF (.pdf)")

    print(f"\nВсего распознано строк: {len(rows)}")
    if rows:
        print(f"Пример первой строки: {rows[0]}")
    return rows, full_text


# =================================================================
# СТАРЫЕ ПАРСЕРЫ (fallback)
# =================================================================
def parse_table_from_text(text):
    """Парсинг табличных данных из текста"""
    rows = []
    lines = text.split('\n')

    in_table = False
    for line in lines:
        line = line.strip()
        if not line:
            continue

        if '№' in line and ('Товар' in line or 'Код' in line or 'Наименование' in line):
            in_table = True
            continue

        if in_table and any(word in line.upper() for word in ['ИТОГО:', 'ВСЕГО:', 'НАИМЕНОВАНИЙ', 'НДС']):
            in_table = False
            continue

        if in_table:
            parts = re.split(r'\s{2,}|\t', line)
            parts = [p.strip() for p in parts if p.strip()]

            if len(parts) >= 3:
                has_numbers = False
                for cell in parts:
                    try:
                        val = float(str(cell).replace(',', '.').replace(' ', '').replace('₽', '').replace('руб', ''))
                        if val > 0:
                            has_numbers = True
                            break
                    except:
                        pass

                if has_numbers:
                    normalized_row = [''] * 11
                    normalized_row[10] = 'RUB'

                    if len(parts) >= 7:
                        normalized_row[0] = parts[0]
                        normalized_row[1] = parts[1] if len(parts) > 1 else ''
                        normalized_row[2] = parts[2] if len(parts) > 2 else ''
                        normalized_row[3] = parts[3] if len(parts) > 3 else ''
                        normalized_row[4] = parts[4] if len(parts) > 4 else ''
                        normalized_row[5] = parts[5] if len(parts) > 5 else ''
                        normalized_row[6] = parts[6] if len(parts) > 6 else ''
                    elif len(parts) >= 5:
                        normalized_row[2] = parts[0]
                        normalized_row[3] = parts[1] if len(parts) > 1 else ''
                        normalized_row[4] = parts[2] if len(parts) > 2 else ''
                        normalized_row[5] = parts[3] if len(parts) > 3 else ''
                        normalized_row[6] = parts[4] if len(parts) > 4 else ''

                    rows.append(normalized_row)

    return rows


def extract_table_from_image(image):
    """Извлечение табличных данных из изображения"""
    try:
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        rows = []
        current_row = []
        last_y = -1

        for i in range(len(data['text'])):
            if int(data['conf'][i]) > -1 and data['text'][i].strip():
                y = data['top'][i]
                if last_y != -1 and abs(y - last_y) > 10:
                    if current_row:
                        rows.append(current_row)
                    current_row = []
                current_row.append(data['text'][i])
                last_y = y

        if current_row:
            rows.append(current_row)

        return rows
    except Exception as e:
        print(f"Ошибка извлечения таблицы из изображения: {e}")
        return []


def parse_invoice_from_text(text):
    """Парсинг счетов на оплату из текстового представления"""
    rows = []
    lines = text.split('\n')

    in_items_section = False
    current_row_parts = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        if any(keyword in line_stripped.upper() for keyword in ['№', 'КОД', 'ТОВАРЫ', 'НАИМЕНОВАНИЕ']):
            in_items_section = True
            continue

        if in_items_section and any(keyword in line_stripped.upper() for keyword in ['ИТОГО', 'ВСЕГО', 'НАИМЕНОВАНИЙ']):
            in_items_section = False
            continue

        if in_items_section:
            parts = re.split(r'\s{3,}|\t+', line_stripped)
            parts = [p.strip() for p in parts if p.strip()]

            if len(parts) >= 3:
                numbers_found = []
                for part in parts:
                    cleaned = part.replace(' ', '').replace(',', '.').replace('₽', '').replace('руб', '')
                    try:
                        val = float(cleaned)
                        if val > 0:
                            numbers_found.append((part, val))
                    except:
                        pass

                if len(numbers_found) >= 2:
                    number = parts[0] if parts[0].isdigit() else str(len(rows) + 1)
                    code = parts[1] if len(parts) > 1 and not parts[1][0].isalpha() else ''
                    name = ' '.join([p for p in parts[2:] if not any(char.isdigit() for char in p)])[:100]

                    quantity = "1"
                    price = "0"
                    total = "0"

                    numeric_values = [val for _, val in numbers_found]
                    if len(numeric_values) >= 3:
                        quantity = str(int(numeric_values[0]))
                        price = f"{numeric_values[1]:.2f}"
                        total = f"{numeric_values[2]:.2f}"
                    elif len(numeric_values) == 2:
                        quantity = str(int(numeric_values[0]))
                        price = f"{numeric_values[1]:.2f}"
                        total = f"{float(quantity) * float(price):.2f}"

                    unit = "шт."
                    delivery = ""

                    normalized_row = [
                        number, code, name, quantity, unit, price, total, delivery, "", "", "RUB"
                    ]
                    rows.append(normalized_row)
                    print(f"[TEXT PARSE] Строка {len(rows)}: {name[:30]}... кол-во={quantity}, цена={price}")

    return rows