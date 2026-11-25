# -*- coding: utf-8 -*-
"""Извлечение данных из письма и автопривязка к заказу/счёту.

Инвойсы, даты, суммы, трек-номера, сроки поставки; обещанная дата сравнивается
с ETA заказа.Regex подобраны под реальные форматы: TE-4855, VEK261014-1,
26080413, 0261112.PQ.DEVTEK, «Поставка 43», «8 weeks», «1 326 494,40».
"""
import re
from datetime import datetime

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
          "янв": 1, "фев": 2, "мар": 3, "апр": 4, "мая": 5, "май": 5, "июн": 6,
          "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12}

RE_INVOICE_CTX = re.compile(
    r"(?:инвойс|invoice|inv\.?|проформа|proforma|счёт|счет|сч\.?|№|no\.?|number)"
    r"\s*[№:#]?\s*([A-ZА-Я0-9][A-ZА-Я0-9./\-]{3,24})", re.I)
RE_INVOICE_PAT = re.compile(r"\b([A-Z]{2,6}\d{4,10}(?:-\d{1,4})?|[A-Z]{2,4}-\d{3,8})\b")
RE_INVOICE_DOT = re.compile(r"\b(\d{6,8}\.[A-Z]{2,4}\.[A-Z]{3,10})\b")
RE_DELIVERY = re.compile(r"(?:поставк\w*|delivery|shipment)\s*[№:#]?\s*(\d{1,4})", re.I)

RE_DATE_NUM = re.compile(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})\b")
RE_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_DATE_TXT = re.compile(r"\b(\d{1,2})\s*([A-Za-zА-Яа-я]{3,9})\.?\s*(\d{4})\b")
RE_DATE_TXT2 = re.compile(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})\b")

RE_AMOUNT = re.compile(
    r"(?:(EUR|USD|CNY|RUB|TRY|₽|€|\$|¥|₺)\s*)?"
    r"(\d{1,3}(?:[ \u00a0.,]\d{3})+(?:[.,]\d{1,2})?|\d+[.,]\d{2})"
    r"\s*(EUR|USD|CNY|RUB|TRY|₽|€|\$|¥|₺|руб\w*|р\.)?", re.I)

RE_TRACK = [
    ("SF Express", re.compile(r"\bSF\d{12,15}\b")),
    ("UPS", re.compile(r"\b1Z[0-9A-Z]{16}\b")),
    ("DHL", re.compile(r"\b(?:DHL[:\s]*)?(\d{10})\b", re.I)),
    ("EMS/почта", re.compile(r"\b[A-Z]{2}\d{9}[A-Z]{2}\b")),
    ("Почта РФ", re.compile(r"\b\d{14}\b")),
    ("JD", re.compile(r"\bJD[A-Z0-9]{10,18}\b")),
    ("Трек", re.compile(r"(?:трек|tracking|awb|waybill)[\s№:#]*([A-Z0-9]{8,20})", re.I)),
]

RE_TERM = re.compile(
    r"(\d{1,3})(?:\s*[-–]\s*\d{1,3})?\s*"
    r"(weeks?|нед\w*|days?|дн\w*|дней|рабочих\s+дн\w*|months?|мес\w*)", re.I)

RE_PROMISE = re.compile(
    r"(?:поставк\w*|отгруз\w*|delivery|ship\w*|готов\w*|ready|dispatch|eta)"
    r"[^.。\n]{0,60}?(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4}-\d{2}-\d{2})", re.I)

CUR_MAP = {"€": "EUR", "$": "USD", "¥": "CNY", "₽": "RUB", "₺": "TRY"}


def _norm_amount(s):
    s = (s or "").replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _norm_cur(c):
    if not c:
        return ""
    c = c.strip()
    if c in CUR_MAP:
        return CUR_MAP[c]
    up = c.upper()
    if up.startswith("РУБ") or up == "Р.":
        return "RUB"
    return up if up in ("EUR", "USD", "CNY", "RUB", "TRY") else ""


def parse_date(s):
    """ДД.ММ.ГГГГ / ДД.ММ.ГГ / ГГГГ-ММ-ДД / 12 Feb 2027 / Feb 12, 2027."""
    s = (s or "").strip()
    if not s:
        return None
    m = RE_DATE_ISO.fullmatch(s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = RE_DATE_NUM.fullmatch(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            return datetime(y, mo, d)
        except ValueError:
            return None
    m = RE_DATE_TXT.fullmatch(s)
    if m:
        mo = MONTHS.get(m.group(2)[:3].lower())
        if mo:
            try:
                return datetime(int(m.group(3)), mo, int(m.group(1)))
            except ValueError:
                return None
    m = RE_DATE_TXT2.fullmatch(s)
    if m:
        mo = MONTHS.get(m.group(1)[:3].lower())
        if mo:
            try:
                return datetime(int(m.group(3)), mo, int(m.group(2)))
            except ValueError:
                return None
    return None


def extract_all(subject, body):
    """Возвращает словарь списков: invoices, deliveries, dates, amounts, tracks, terms, promises."""
    text = f"{subject or ''}\n{body or ''}"
    out = {"invoices": [], "deliveries": [], "dates": [], "amounts": [],
           "tracks": [], "terms": [], "promises": []}
    seen = {k: set() for k in out}

    def put(kind, value, extra=""):
        key = str(value).upper()
        if key and key not in seen[kind]:
            seen[kind].add(key)
            out[kind].append({"value": value, "extra": extra})

    for m in RE_INVOICE_CTX.finditer(text):
        v = m.group(1).rstrip(".,;:)")
        if len(v) >= 4 and any(ch.isdigit() for ch in v):
            put("invoices", v, "по контексту")
    for rx in (RE_INVOICE_PAT, RE_INVOICE_DOT):
        for m in rx.finditer(text):
            put("invoices", m.group(1), "по шаблону")
    for m in RE_DELIVERY.finditer(text):
        put("deliveries", m.group(1))

    for rx in (RE_DATE_NUM, RE_DATE_ISO, RE_DATE_TXT, RE_DATE_TXT2):
        for m in rx.finditer(text):
            raw = m.group(0)
            d = parse_date(raw)
            if d and 2000 <= d.year <= 2100:
                put("dates", d.strftime("%d.%m.%Y"), raw)
    for m in RE_PROMISE.finditer(text):
        d = parse_date(m.group(1))
        if d:
            put("promises", d.strftime("%d.%m.%Y"))

    for m in RE_AMOUNT.finditer(text):
        cur = _norm_cur(m.group(1) or m.group(3) or "")
        val = _norm_amount(m.group(2))
        if val <= 0:
            continue
        if not cur and not re.search(r"[.,]\d{2}$", m.group(2)):
            continue                      # без валюты и без копеек — скорее артикул
        put("amounts", f"{val:.2f}", cur)

    for label, rx in RE_TRACK:
        for m in rx.finditer(text):
            v = m.group(1) if m.groups() else m.group(0)
            if len(v) >= 8:
                put("tracks", v, label)

    for m in RE_TERM.finditer(text):
        n = int(m.group(1))
        unit = m.group(2).lower()
        if "нед" in unit or "week" in unit:
            u = "Недели"
        elif "мес" in unit or "month" in unit:
            u = "Месяцы"
        elif "рабоч" in unit:
            u = "Рабочие дни"
        else:
            u = "Календарные дни"
        if 0 < n <= 365:
            put("terms", str(n), u)
    return out


def find_order(db_manager, project_name, extracted):
    """Ищет заказ по инвойсу/номеру поставки. Возвращает (batch_id, invoice, note)."""
    invoices = [i["value"] for i in extracted.get("invoices", [])]
    deliveries = [d["value"] for d in extracted.get("deliveries", [])]
    if not invoices and not deliveries:
        return 0, "", ""
    try:
        rows = db_manager.conn.execute(
            """SELECT order_batch_id, MAX(invoice_number) inv, MAX(delivery_number) dn
               FROM orders WHERE project_name=? GROUP BY order_batch_id""",
            (project_name or "",)).fetchall()
    except Exception:
        return 0, "", ""
    norm = lambda s: re.sub(r"[\s\-./]", "", str(s or "")).upper()
    for r in rows:
        inv = norm(r["inv"])
        if inv:
            for v in invoices:
                nv = norm(v)
                if nv and (nv == inv or nv in inv or inv in nv):
                    return r["order_batch_id"], r["inv"], "по инвойсу"
        dn = re.sub(r"\D", "", str(r["dn"] or ""))
        if dn:
            for d in deliveries:
                if d == dn:
                    return r["order_batch_id"], r["inv"] or "", "по номеру поставки"
    return 0, "", ""


def apply_to_message(mail_db, db_manager, msg_id, msg, types):
    """Классификация + извлечение + привязка. Возвращает сводку для журнала."""
    subject, body = msg.get("subject", ""), msg.get("body", "")
    st = mail_db.get_settings()
    wt, risk, risk_words, actions = mail_db.classify(subject, body, types,
                                                     st.get("default_type") or "")
    mail_db.set_field(msg_id, "work_type", wt)
    if risk:
        mail_db.set_field(msg_id, "risk_flag", 1)
        mail_db.set_field(msg_id, "risk_words", risk_words)

    ex = extract_all(subject, body)
    for kind, items in ex.items():
        for it in items:
            mail_db.add_extracted(msg_id, kind[:-1] if kind.endswith("s") else kind,
                                  it["value"], it["extra"])

    batch, invoice, how = find_order(db_manager, msg.get("project_name", ""), ex)
    if batch:
        mail_db.link_order(msg_id, batch, invoice)

    promise_shift = ""
    if batch and ex["promises"]:
        try:
            cur = db_manager.get_order_status(batch) or {}
            eta = parse_date(cur.get("eta_date") or "")
            new = parse_date(ex["promises"][0]["value"])
            if eta and new and new.date() != eta.date():
                promise_shift = (f"обещано {new:%d.%m.%Y}, в плане {eta:%d.%m.%Y} "
                                 f"({(new - eta).days:+d} дн)")
        except Exception:
            pass

    return {"type": wt, "risk": risk_words, "actions": actions,
            "batch_id": batch, "invoice": invoice, "link_how": how,
            "promise_shift": promise_shift,
            "counts": {k: len(v) for k, v in ex.items() if v}}
