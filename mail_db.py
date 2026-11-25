# -*- coding: utf-8 -*-
"""Отдельная БД переписки (mail.db): письма, тела, треды, статусы, привязки,
извлечённые данные, вложения. Синхронизируется с облаком независимо от projects.db.

Пароль почты хранится ЛОКАЛЬНО (mail_local.json) и в облако не попадает.
"""
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime

MAIL_STATUSES = ["Новое", "В работе", "Ждём ответа", "Закрыто"]

_RE_PREFIX = re.compile(r"^\s*((re|fwd?|fw|ответ|пересылка)\s*(\[\d+\])?\s*:\s*)+", re.I)
_RE_QUOTE = re.compile(
    r"(?im)^\s*(>{1,}.*|-{2,}\s*original message\s*-{2,}|_{5,}|"
    r"on .{5,80} wrote:|в сообщении .{5,80} пишет:|"
    r"отправлено из .*|sent from .*)$")


def norm_subject(s):
    """Тема без Re:/Fwd: — ключ треда."""
    s = _RE_PREFIX.sub("", s or "")
    return re.sub(r"\s+", " ", s).strip().lower()


def trim_quotes(body):
    """Обрезает цитаты и подписи — экономия 60–80 % объёма."""
    if not body:
        return "", 0
    full = len(body)
    out, quoted = [], 0
    for ln in body.split("\n"):
        if _RE_QUOTE.match(ln):
            break
        if ln.lstrip().startswith(">"):
            quoted += 1
            if quoted > 2:
                break
            continue
        quoted = 0
        out.append(ln)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    if len(text) < 40 and full > 200:
        text = body.strip()
    return text[:100000], full


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paths():
    try:
        from paths import DATA_DIR, LOCAL_DIR
        return DATA_DIR, LOCAL_DIR
    except Exception:
        here = os.path.dirname(os.path.abspath(__file__))
        return here, here


class MailDatabase:
    def __init__(self, db_path=None, log=print):
        self.log = log
        data_dir, local_dir = _paths()
        self.db_path = db_path or os.path.join(data_dir, "mail.db")
        self.local_cfg_path = os.path.join(local_dir, "mail_local.json")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # check_same_thread=False: автопроверка и синхронизация работают в потоках
        self.conn = sqlite3.connect(self.db_path, timeout=20, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 20000")
        try:
            self.conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            pass
        self.device = uuid.uuid4().hex[:8]
        self.fts = False
        self._create()

    # ==================================================================
    def _create(self):
        c = self.conn.cursor()
        c.executescript("""
        CREATE TABLE IF NOT EXISTS mail_settings (
            id INTEGER PRIMARY KEY CHECK (id=1),
            host TEXT DEFAULT 'imap.mail.ru',
            port INTEGER DEFAULT 993,
            use_ssl INTEGER DEFAULT 1,
            email TEXT DEFAULT '',
            inbox TEXT DEFAULT 'INBOX',
            sent TEXT DEFAULT '',
            check_sent INTEGER DEFAULT 1,
            limit_msgs INTEGER DEFAULT 300,
            all_projects INTEGER DEFAULT 1,
            default_type TEXT DEFAULT '',
            auto_check INTEGER DEFAULT 0,
            interval_min INTEGER DEFAULT 30,
            sync_auto INTEGER DEFAULT 1,
            sync_interval_min INTEGER DEFAULT 60,
            reply_sla_days INTEGER DEFAULT 2,
            uidvalidity_inbox TEXT DEFAULT '',
            uidvalidity_sent TEXT DEFAULT '',
            last_uid_inbox TEXT DEFAULT '',
            last_uid_sent TEXT DEFAULT '',
            last_check TEXT DEFAULT '',
            last_sync TEXT DEFAULT '');

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            project_name TEXT DEFAULT '',
            folder TEXT NOT NULL,
            uid TEXT NOT NULL,
            message_id TEXT DEFAULT '',
            thread_id TEXT DEFAULT '',
            subject TEXT DEFAULT '',
            subject_norm TEXT DEFAULT '',
            sender TEXT DEFAULT '',
            sender_email TEXT DEFAULT '',
            recipients TEXT DEFAULT '',
            cc TEXT DEFAULT '',
            date_sent TEXT DEFAULT '',
            date_iso TEXT DEFAULT '',
            direction TEXT DEFAULT 'Входящее',
            work_type TEXT DEFAULT '',
            status TEXT DEFAULT 'Новое',
            needs_reply INTEGER DEFAULT 0,
            replied_at TEXT DEFAULT '',
            risk_flag INTEGER DEFAULT 0,
            risk_words TEXT DEFAULT '',
            order_batch_id INTEGER DEFAULT 0,
            invoice_number TEXT DEFAULT '',
            spec_id INTEGER DEFAULT 0,
            att_count INTEGER DEFAULT 0,
            size INTEGER DEFAULT 0,
            body_len INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            device TEXT DEFAULT '',
            UNIQUE(project_id, folder, uid));

        CREATE TABLE IF NOT EXISTS bodies (
            msg_id INTEGER PRIMARY KEY,
            body TEXT DEFAULT '',
            full_len INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT '');

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER NOT NULL,
            name TEXT DEFAULT '',
            sha256 TEXT DEFAULT '',
            size INTEGER DEFAULT 0,
            mime TEXT DEFAULT '',
            remote_path TEXT DEFAULT '',
            local_path TEXT DEFAULT '',
            downloaded_at TEXT DEFAULT '',
            UNIQUE(msg_id, name));

        CREATE TABLE IF NOT EXISTS extracted (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            value TEXT DEFAULT '',
            extra TEXT DEFAULT '',
            UNIQUE(msg_id, kind, value));

        CREATE TABLE IF NOT EXISTS mail_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            work_type TEXT DEFAULT '',
            action TEXT DEFAULT '',
            priority INTEGER DEFAULT 10,
            enabled INTEGER DEFAULT 1);

        CREATE INDEX IF NOT EXISTS idx_msg_proj ON messages(project_id, date_iso);
        CREATE INDEX IF NOT EXISTS idx_msg_thread ON messages(project_id, thread_id);
        CREATE INDEX IF NOT EXISTS idx_msg_status ON messages(project_id, status);
        CREATE INDEX IF NOT EXISTS idx_att_msg ON attachments(msg_id);
        CREATE INDEX IF NOT EXISTS idx_ext_msg ON extracted(msg_id);
        """)
        c.execute("INSERT OR IGNORE INTO mail_settings (id) VALUES (1)")
        c.execute("SELECT COUNT(*) FROM mail_rules")
        if c.fetchone()[0] == 0:
            for kw, wt, act, pr in (
                    ("инвойс", "Поставка", "invoice", 20), ("invoice", "Поставка", "invoice", 20),
                    ("проформа", "Поставка", "invoice", 20), ("proforma", "Поставка", "invoice", 20),
                    ("счёт", "Поставка", "invoice", 18), ("счет", "Поставка", "invoice", 18),
                    ("кп", "Запрос цены", "offer", 15), ("коммерческое", "Запрос цены", "offer", 15),
                    ("packing", "Поставка", "packing", 15), ("упаковочн", "Поставка", "packing", 15),
                    ("трек", "Поставка", "tracking", 15), ("tracking", "Поставка", "tracking", 15),
                    ("awb", "Поставка", "tracking", 15), ("отгруз", "Поставка", "shipping", 15),
                    ("задерж", "", "risk", 30), ("delay", "", "risk", 30),
                    ("отмен", "", "risk", 30), ("cancel", "", "risk", 30),
                    ("брак", "", "risk", 30), ("дефект", "", "risk", 30),
                    ("нет в наличии", "", "risk", 30), ("out of stock", "", "risk", 30),
                    ("таможн", "Поставка", "customs", 20), ("customs", "Поставка", "customs", 20),
                    ("оплат", "Поставка", "payment", 12), ("payment", "Поставка", "payment", 12),
                    ("чертёж", "Проектирование", "design", 12), ("drawing", "Проектирование", "design", 12),
                    ("монтаж", "Монтаж", "mount", 12), ("пусконалад", "Пусконаладка", "start", 12)):
                c.execute("""INSERT OR IGNORE INTO mail_rules (keyword, work_type, action, priority)
                             VALUES (?,?,?,?)""", (kw, wt, act, pr))
        self.conn.commit()
        try:
            c.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                subject, sender, recipients, note, content='messages', content_rowid='id');
            CREATE TRIGGER IF NOT EXISTS msg_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, subject, sender, recipients, note)
                VALUES (new.id, new.subject, new.sender, new.recipients, new.note);
            END;
            CREATE TRIGGER IF NOT EXISTS msg_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, subject, sender, recipients, note)
                VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.note);
                INSERT INTO messages_fts(rowid, subject, sender, recipients, note)
                VALUES (new.id, new.subject, new.sender, new.recipients, new.note);
            END;
            CREATE TRIGGER IF NOT EXISTS msg_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, subject, sender, recipients, note)
                VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.note);
            END;
            """)
            self.conn.commit()
            self.fts = True
        except sqlite3.OperationalError as e:
            self.log(f"[mail_db] FTS5 недоступен, поиск через LIKE: {e}")
            self.fts = False

    def close(self):
        try:
            if self.conn:
                self.conn.close()
        except Exception:
            pass
        self.conn = None

    # ==================================================================
    # Настройки: пароль — только локально
    # ==================================================================
    def get_settings(self):
        r = self.conn.execute("SELECT * FROM mail_settings WHERE id=1").fetchone()
        d = dict(r) if r else {}
        d["password"] = ""
        try:
            with open(self.local_cfg_path, "r", encoding="utf-8") as f:
                loc = json.load(f)
            d["password"] = loc.get("password", "")
            if loc.get("email"):
                d["email"] = loc["email"]
        except Exception:
            pass
        return d

    def save_settings(self, data):
        data = dict(data)
        pwd = data.pop("password", None)
        row = self.conn.execute("SELECT * FROM mail_settings WHERE id=1").fetchone()
        cur = dict(row) if row else {}
        cur.update({k: v for k, v in data.items() if k in cur and k != "id"})
        cols = [k for k in cur if k != "id"]
        self.conn.execute(
            f"UPDATE mail_settings SET {','.join(k + '=?' for k in cols)} WHERE id=1",
            [cur[k] for k in cols])
        self.conn.commit()
        if pwd is not None:
            loc = {}
            try:
                with open(self.local_cfg_path, "r", encoding="utf-8") as f:
                    loc = json.load(f)
            except Exception:
                pass
            loc["password"] = pwd
            loc["email"] = data.get("email", loc.get("email", ""))
            os.makedirs(os.path.dirname(self.local_cfg_path), exist_ok=True)
            with open(self.local_cfg_path, "w", encoding="utf-8") as f:
                json.dump(loc, f, ensure_ascii=False, indent=2)
            try:
                os.chmod(self.local_cfg_path, 0o600)
            except OSError:
                pass

    # ==================================================================
    # Письма
    # ==================================================================
    def exists(self, project_id, folder, uid):
        return self.conn.execute(
            "SELECT id FROM messages WHERE project_id=? AND folder=? AND uid=?",
            (project_id, folder, str(uid))).fetchone()

    def add_message(self, m, body=""):
        """Дедуп по (проект, папка, UID). Возвращает id или None если уже есть."""
        if self.exists(m["project_id"], m["folder"], m["uid"]):
            return None
        text, full_len = trim_quotes(body)
        subj = m.get("subject", "")
        snorm = norm_subject(subj)
        thread = f'{m["project_id"]}:{snorm}' if snorm else f'{m["project_id"]}:msg{m["uid"]}'
        sender = m.get("sender", "")
        em = re.search(r"[\w.+-]+@[\w.-]+", sender)
        now = _now()
        cur = self.conn.execute("""INSERT INTO messages
            (project_id, project_name, folder, uid, message_id, thread_id, subject, subject_norm,
             sender, sender_email, recipients, cc, date_sent, date_iso, direction, work_type,
             status, needs_reply, risk_flag, risk_words, order_batch_id, invoice_number, spec_id,
             att_count, size, body_len, note, created_at, updated_at, device)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m["project_id"], m.get("project_name", ""), m["folder"], str(m["uid"]),
             m.get("message_id", ""), thread, subj, snorm, sender,
             em.group(0).lower() if em else "", m.get("recipients", ""), m.get("cc", ""),
             m.get("date_sent", ""), m.get("date_iso", ""), m.get("direction", "Входящее"),
             m.get("work_type", ""), "Новое",
             1 if m.get("direction") == "Входящее" else 0,
             m.get("risk_flag", 0), m.get("risk_words", ""),
             m.get("order_batch_id", 0), m.get("invoice_number", ""), m.get("spec_id", 0),
             m.get("att_count", 0), m.get("size", 0), len(text), "", now, now, self.device))
        mid = cur.lastrowid
        self.conn.execute(
            "INSERT OR REPLACE INTO bodies (msg_id, body, full_len, updated_at) VALUES (?,?,?,?)",
            (mid, text, full_len, now))
        self.conn.commit()
        return mid

    def get_messages(self, project_id, work_type=None, direction=None, status=None,
                     search=None, only_unanswered=False, only_risk=False,
                     threads=True, limit=800):
        q = """SELECT m.*, (SELECT COUNT(*) FROM messages x
                            WHERE x.project_id=m.project_id AND x.thread_id=m.thread_id) AS thread_n
               FROM messages m WHERE m.project_id=?"""
        p = [project_id]
        if work_type:
            q += " AND m.work_type=?"
            p.append(work_type)
        if direction:
            q += " AND m.direction=?"
            p.append(direction)
        if status:
            q += " AND m.status=?"
            p.append(status)
        if only_unanswered:
            q += " AND m.needs_reply=1 AND m.replied_at='' AND m.direction='Входящее'"
        if only_risk:
            q += " AND m.risk_flag=1"
        if search:
            if self.fts:
                q += (" AND (m.id IN (SELECT rowid FROM messages_fts WHERE messages_fts MATCH ?)"
                      " OR m.id IN (SELECT msg_id FROM bodies WHERE body LIKE ?))")
                p += [f'"{search}"', f"%{search}%"]
            else:
                q += (" AND (m.subject LIKE ? OR m.sender LIKE ? OR m.recipients LIKE ?"
                      " OR m.id IN (SELECT msg_id FROM bodies WHERE body LIKE ?))")
                p += [f"%{search}%"] * 4
        if threads:
            q += (" AND m.id=(SELECT x.id FROM messages x WHERE x.project_id=m.project_id"
                  " AND x.thread_id=m.thread_id ORDER BY x.date_iso DESC, x.id DESC LIMIT 1)")
        q += " ORDER BY m.date_iso DESC, m.id DESC LIMIT ?"
        p.append(limit)
        return self.conn.execute(q, p).fetchall()

    def get_thread(self, project_id, thread_id):
        return self.conn.execute(
            """SELECT * FROM messages WHERE project_id=? AND thread_id=?
               ORDER BY date_iso, id""", (project_id, thread_id)).fetchall()

    def get_message(self, msg_id):
        r = self.conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
        return dict(r) if r else {}

    def get_body(self, msg_id):
        r = self.conn.execute("SELECT body FROM bodies WHERE msg_id=?", (msg_id,)).fetchone()
        return r["body"] if r else ""

    def _touch(self, msg_id):
        self.conn.execute("UPDATE messages SET updated_at=?, device=? WHERE id=?",
                          (_now(), self.device, msg_id))

    def set_field(self, msg_id, field, value):
        allowed = {"work_type", "status", "note", "needs_reply", "replied_at",
                   "order_batch_id", "invoice_number", "spec_id", "risk_flag", "risk_words"}
        if field not in allowed:
            raise ValueError(field)
        self.conn.execute(f"UPDATE messages SET {field}=? WHERE id=?", (value, msg_id))
        self._touch(msg_id)
        self.conn.commit()

    def set_status(self, msg_id, status):
        self.set_field(msg_id, "status", status)
        if status == "Закрыто":
            self.set_field(msg_id, "needs_reply", 0)

    def mark_replied(self, msg_id):
        self.set_field(msg_id, "replied_at", _now())
        self.set_field(msg_id, "needs_reply", 0)
        self.set_field(msg_id, "status", "Ждём ответа")

    def link_order(self, msg_id, batch_id, invoice=""):
        self.conn.execute("UPDATE messages SET order_batch_id=?, invoice_number=? WHERE id=?",
                          (int(batch_id or 0), invoice or "", msg_id))
        self._touch(msg_id)
        self.conn.commit()

    def delete_message(self, msg_id):
        with self.conn:
            self.conn.execute("DELETE FROM bodies WHERE msg_id=?", (msg_id,))
            self.conn.execute("DELETE FROM attachments WHERE msg_id=?", (msg_id,))
            self.conn.execute("DELETE FROM extracted WHERE msg_id=?", (msg_id,))
            self.conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))

    # ==================================================================
    # Вложения и извлечённые данные
    # ==================================================================
    def add_attachment(self, msg_id, name, sha256="", size=0, mime="", remote_path=""):
        try:
            self.conn.execute("""INSERT OR IGNORE INTO attachments
                (msg_id, name, sha256, size, mime, remote_path) VALUES (?,?,?,?,?,?)""",
                (msg_id, name, sha256, size, mime, remote_path))
            self.conn.execute(
                "UPDATE messages SET att_count=(SELECT COUNT(*) FROM attachments WHERE msg_id=?) "
                "WHERE id=?", (msg_id, msg_id))
            self.conn.commit()
        except sqlite3.Error as e:
            self.log(f"[mail_db] attachment: {e}")

    def get_attachments(self, msg_id):
        return self.conn.execute("SELECT * FROM attachments WHERE msg_id=? ORDER BY id",
                                 (msg_id,)).fetchall()

    def set_attachment_local(self, att_id, local_path):
        self.conn.execute("UPDATE attachments SET local_path=?, downloaded_at=? WHERE id=?",
                          (local_path, _now(), att_id))
        self.conn.commit()

    def add_extracted(self, msg_id, kind, value, extra=""):
        if not value:
            return
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO extracted (msg_id, kind, value, extra) VALUES (?,?,?,?)",
                (msg_id, kind, str(value)[:200], extra))
            self.conn.commit()
        except sqlite3.Error:
            pass

    def get_extracted(self, msg_id):
        return self.conn.execute("SELECT * FROM extracted WHERE msg_id=? ORDER BY kind, id",
                                 (msg_id,)).fetchall()

    # ==================================================================
    # Правила классификации
    # ==================================================================
    def get_rules(self):
        return self.conn.execute(
            "SELECT * FROM mail_rules WHERE enabled=1 ORDER BY priority DESC").fetchall()

    def add_rule(self, keyword, work_type="", action="", priority=10):
        kw = (keyword or "").lower().strip()
        if not kw:
            return False
        try:
            self.conn.execute(
                "INSERT OR REPLACE INTO mail_rules (keyword, work_type, action, priority) "
                "VALUES (?,?,?,?)", (kw, work_type, action, priority))
            self.conn.commit()
            return True
        except sqlite3.Error:
            return False

    def delete_rule(self, rule_id):
        self.conn.execute("DELETE FROM mail_rules WHERE id=?", (rule_id,))
        self.conn.commit()

    def classify(self, subject, body, types, default=""):
        """Возвращает (work_type, risk_flag, risk_words, actions)."""
        low = (subject or "").lower()
        text = low + " " + (body or "").lower()[:4000]
        wt, risks, actions = "", [], []
        for r in self.get_rules():
            kw = r["keyword"]
            if kw and kw in text:
                if r["action"] == "risk":
                    risks.append(kw)
                elif r["action"]:
                    actions.append(r["action"])
                if not wt and r["work_type"] and r["work_type"] in types:
                    wt = r["work_type"]
        if not wt:
            for t in types:
                if t and t.lower() in low:
                    wt = t
                    break
        if not wt:
            for t in types:
                if t and t.lower() in text:
                    wt = t
                    break
        return (wt or default or (types[0] if types else ""),
                1 if risks else 0, ", ".join(risks), actions)

    # ==================================================================
    # Контроль и сводки
    # ==================================================================
    def unanswered_ids(self, project_id=None, sla_days=2):
        """Письма без ответа дольше SLA. Без JOIN — имя проекта подставляет вызывающий."""
        q = """SELECT * FROM messages
               WHERE direction='Входящее' AND needs_reply=1 AND replied_at=''
                 AND status!='Закрыто'
                 AND date_iso!='' 
                 AND julianday('now') - julianday(substr(date_iso,1,10)) >= ?"""
        p = [sla_days]
        if project_id:
            q += " AND project_id=?"
            p.append(project_id)
        return self.conn.execute(q + " ORDER BY date_iso", p).fetchall()

    def unanswered(self, project_id=None, sla_days=2):
        """Совместимость: то же, что unanswered_ids."""
        return self.unanswered_ids(project_id, sla_days)

    def stats(self, project_id):
        r = self.conn.execute("""SELECT COUNT(*) n,
                SUM(CASE WHEN status='Новое' THEN 1 ELSE 0 END) new,
                SUM(CASE WHEN needs_reply=1 AND replied_at='' AND direction='Входящее'
                         AND status!='Закрыто' THEN 1 ELSE 0 END) wait,
                SUM(CASE WHEN risk_flag=1 THEN 1 ELSE 0 END) risk,
                SUM(CASE WHEN direction='Входящее' THEN 1 ELSE 0 END) inc,
                SUM(CASE WHEN direction='Исходящее' THEN 1 ELSE 0 END) out,
                SUM(CASE WHEN order_batch_id>0 THEN 1 ELSE 0 END) linked
            FROM messages WHERE project_id=?""", (project_id,)).fetchone()
        return {k: (r[k] or 0) for k in ("n", "new", "wait", "risk", "inc", "out", "linked")}

    def db_size_mb(self):
        try:
            return os.path.getsize(self.db_path) / 1048576
        except OSError:
            return 0.0

    # ==================================================================
    # Слияние при синхронизации (last-write-wins по updated_at)
    # ==================================================================
    MERGE_FIELDS = ("work_type", "status", "needs_reply", "replied_at", "note",
                    "risk_flag", "risk_words", "order_batch_id", "invoice_number", "spec_id")

    def merge_from(self, other_path):
        """Объединяет письма из другой mail.db. Возвращает (добавлено, обновлено)."""
        if not os.path.isfile(other_path):
            return 0, 0
        src = sqlite3.connect(other_path)
        src.row_factory = sqlite3.Row
        added = updated = 0
        try:
            for r in src.execute("SELECT * FROM messages").fetchall():
                mine = self.exists(r["project_id"], r["folder"], r["uid"])
                b = src.execute("SELECT body, full_len FROM bodies WHERE msg_id=?",
                                (r["id"],)).fetchone()
                if mine is None:
                    data = dict(r)
                    data.pop("id", None)
                    cols = list(data.keys())
                    cur = self.conn.execute(
                        f"INSERT INTO messages ({','.join(cols)}) "
                        f"VALUES ({','.join('?' for _ in cols)})",
                        [data[c] for c in cols])
                    mid = cur.lastrowid
                    if b:
                        self.conn.execute(
                            "INSERT OR REPLACE INTO bodies VALUES (?,?,?,?)",
                            (mid, b["body"], b["full_len"], _now()))
                    for a in src.execute("SELECT * FROM attachments WHERE msg_id=?", (r["id"],)):
                        self.add_attachment(mid, a["name"], a["sha256"], a["size"],
                                            a["mime"], a["remote_path"])
                    for e in src.execute("SELECT * FROM extracted WHERE msg_id=?", (r["id"],)):
                        self.add_extracted(mid, e["kind"], e["value"], e["extra"])
                    added += 1
                else:
                    mid = mine["id"]
                    row = self.conn.execute("SELECT updated_at FROM messages WHERE id=?",
                                            (mid,)).fetchone()
                    mine_ts = (row["updated_at"] or "") if row else ""
                    if (r["updated_at"] or "") > mine_ts:
                        sets = ",".join(f"{f}=?" for f in self.MERGE_FIELDS)
                        self.conn.execute(
                            f"UPDATE messages SET {sets}, updated_at=?, device=? WHERE id=?",
                            [r[f] for f in self.MERGE_FIELDS] +
                            [r["updated_at"], r["device"], mid])
                        updated += 1
                    if b and not self.get_body(mid):
                        self.conn.execute("INSERT OR REPLACE INTO bodies VALUES (?,?,?,?)",
                                          (mid, b["body"], b["full_len"], _now()))
            for r in src.execute("SELECT * FROM mail_rules").fetchall():
                self.conn.execute(
                    "INSERT OR IGNORE INTO mail_rules (keyword, work_type, action, priority) "
                    "VALUES (?,?,?,?)",
                    (r["keyword"], r["work_type"], r["action"], r["priority"]))
            self.conn.commit()
        finally:
            src.close()
        return added, updated
