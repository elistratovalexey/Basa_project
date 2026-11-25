# -*- coding: utf-8 -*-
"""IMAP Mail.ru: инкрементальное чтение писем проекта + вложения.

Инкремент: храним UIDVALIDITY и последний UID папки. При совпадении UIDVALIDITY
читаем только новые письма, при смене — полный перескан последних N.
"""
import email
import hashlib
import imaplib
import os
import re
import socket
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

MAX_ATT_MB = 25          # вложения крупнее — не тянем


class MailError(Exception):
    pass


def _dec(v):
    if not v:
        return ""
    try:
        return str(make_header(decode_header(v))).strip()
    except Exception:
        return str(v).strip()


def _strip_html(html):
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</(p|div|tr)>", "\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&#39;", "'"), ("&mdash;", "—")):
        html = html.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", html).strip()


def _parts(msg):
    """Возвращает (текст, [вложения: name/data/mime/size])."""
    text, html, files = [], [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = _dec(part.get_filename() or "")
        disp = (part.get("Content-Disposition") or "").lower()
        is_att = bool(name) and ("attachment" in disp or "inline" in disp)
        if is_att:
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:
                data = b""
            if len(data) <= MAX_ATT_MB * 1048576:
                files.append({"name": name, "data": data,
                              "mime": part.get_content_type(), "size": len(data)})
            else:
                files.append({"name": name, "data": b"", "mime": part.get_content_type(),
                              "size": len(data), "skipped": True})
            continue
        if part.get_content_type() not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            cs = part.get_content_charset() or "utf-8"
            try:
                s = payload.decode(cs, errors="replace")
            except LookupError:
                s = payload.decode("utf-8", errors="replace")
        except Exception:
            continue
        (text if part.get_content_type() == "text/plain" else html).append(s)
    body = "\n".join(text).strip() or _strip_html("\n".join(html))
    return body, files


class MailClient:
    def __init__(self, cfg, log=print, timeout=90):
        self.cfg = cfg
        self.log = log
        self.timeout = timeout
        self.conn = None

    # ---------- соединение ----------
    def connect(self):
        host = self.cfg.get("host") or "imap.mail.ru"
        port = int(self.cfg.get("port") or 993)
        user = (self.cfg.get("email") or "").strip()
        pwd = self.cfg.get("password") or ""
        if not user or not pwd:
            raise MailError("Не заданы e-mail или пароль приложения.\n"
                            "Откройте «Переписка → Настройка почты».")
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            self.conn = (imaplib.IMAP4_SSL(host, port) if int(self.cfg.get("use_ssl", 1))
                         else imaplib.IMAP4(host, port))
            self.conn.login(user, pwd)
        except imaplib.IMAP4.error as e:
            raise MailError(f"Вход не выполнен: {e}\n"
                            "Mail.ru требует ПАРОЛЬ ДЛЯ ВНЕШНИХ ПРИЛОЖЕНИЙ "
                            "(Настройки аккаунта → Пароли для внешних приложений).")
        except Exception as e:
            raise MailError(f"Соединение с {host}:{port} не удалось: {e}")
        finally:
            socket.setdefaulttimeout(old)
        return True

    def close(self):
        try:
            if self.conn:
                self.conn.logout()
        except Exception:
            pass
        self.conn = None

    def folders(self):
        out = []
        try:
            typ, data = self.conn.list()
            for raw in data or []:
                s = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
                m = re.match(r'\((?P<flags>[^)]*)\)\s+"(?P<d>[^"]*)"\s+(?P<name>.+)$', s)
                if not m:
                    continue
                name = m.group("name").strip()
                if name.startswith('"') and name.endswith('"'):
                    name = name[1:-1]
                out.append({"name": name, "flags": m.group("flags")})
        except Exception as e:
            self.log(f"[mail] LIST: {e}")
        return out

    def sent_folder(self):
        if self.cfg.get("sent"):
            return self.cfg["sent"]
        for f in self.folders():
            if "\\Sent" in f["flags"]:
                return f["name"]
        return ""

    def _select(self, folder):
        typ, _ = self.conn.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            raise MailError(f"Папка недоступна: {folder}")
        uv = ""
        try:
            t, v = self.conn.response("UIDVALIDITY")
            if v and v[0]:
                uv = v[0].decode() if isinstance(v[0], bytes) else str(v[0])
        except Exception:
            pass
        return uv

    # ---------- чтение ----------
    def _uids(self, folder_key, uidvalidity, limit, mail_db=None):
        """Список UID для обработки + признак полного перескана."""
        st = mail_db.get_settings() if mail_db else {}
        uv_key = f"uidvalidity_{folder_key}"
        uid_key = f"last_uid_{folder_key}"
        saved_uv = str(st.get(uv_key) or "")
        saved_uid = str(st.get(uid_key) or "")
        full = True
        if mail_db and saved_uv and saved_uv == uidvalidity and saved_uid.isdigit():
            nxt = int(saved_uid) + 1
            typ, data = self.conn.uid("search", None, "UID", f"{nxt}:*")
            if typ == "OK":
                uids = [u for u in (data[0] or b"").split()
                        if u.isdigit() and int(u) >= nxt]
                if uids:
                    return sorted(uids, key=int), False
                return [], False
        typ, data = self.conn.uid("search", None, "ALL")
        if typ != "OK":
            return [], True
        uids = (data[0] or b"").split()
        return uids[-int(limit):], full

    def fetch_new(self, folder, folder_key, direction, projects, mail_db=None,
                  limit=300, progress=None):
        """Возвращает (список писем, последний UID, UIDVALIDITY)."""
        uv = self._select(folder)
        uids, full = self._uids(folder_key, uv, limit, mail_db)
        mode = "полный перескан" if full else "только новые"
        self.log(f"[mail] {folder}: {len(uids)} писем ({mode})")
        found, last_uid = [], ""
        total = len(uids)
        for i, uid in enumerate(reversed(uids), 1):
            us = uid.decode() if isinstance(uid, bytes) else str(uid)
            if not last_uid or int(us) > int(last_uid):
                last_uid = us
            if progress and (i % 10 == 0 or i == total):
                progress(f"{folder}: {i}/{total}")
            try:
                typ, hd = self.conn.uid(
                    "fetch", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE)])")
                if typ != "OK" or not hd or not isinstance(hd[0], tuple):
                    continue
                head = email.message_from_bytes(hd[0][1])
                subject = _dec(head.get("Subject"))
                low = subject.lower()
                hits = [p for p in projects if p["name"] and p["name"].lower() in low]
                if not hits:
                    continue
                proj = max(hits, key=lambda p: len(p["name"]))
                if mail_db and mail_db.exists(proj["id"], folder, us):
                    continue
                typ, fd = self.conn.uid("fetch", uid, "(BODY.PEEK[] RFC822.SIZE)")
                if typ != "OK" or not fd or not isinstance(fd[0], tuple):
                    continue
                msg = email.message_from_bytes(fd[0][1])
                body, files = _parts(msg)
                size = 0
                m = re.search(rb"RFC822\.SIZE\s+(\d+)", fd[0][0] or b"")
                if m:
                    size = int(m.group(1))
                ds = head.get("Date") or ""
                try:
                    dt = parsedate_to_datetime(ds)
                    date_iso = dt.strftime("%Y-%m-%d %H:%M:%S")
                    date_sent = dt.strftime("%d.%m.%Y %H:%M")
                except Exception:
                    date_iso, date_sent = "", _dec(ds)
                found.append({
                    "project_id": proj["id"], "project_name": proj["name"],
                    "folder": folder, "uid": us,
                    "message_id": _dec(msg.get("Message-ID")),
                    "subject": subject, "sender": _dec(head.get("From")),
                    "recipients": _dec(head.get("To")), "cc": _dec(head.get("Cc")),
                    "date_sent": date_sent, "date_iso": date_iso,
                    "direction": direction, "body": body,
                    "attachments": files, "att_count": len(files), "size": size,
                })
            except Exception as e:
                self.log(f"[mail] uid {us}: {e}")
                continue
        return found, last_uid, uv


class AttachmentStore:
    """Вложения: локальный кэш + выгрузка в облако по sha256 (дедупликация)."""

    def __init__(self, mail_db, log=print):
        self.db = mail_db
        self.log = log
        try:
            from paths import LOCAL_DIR
            base = LOCAL_DIR
        except Exception:
            base = os.path.dirname(os.path.abspath(__file__))
        self.cache = os.path.join(base, "mail_cache")
        os.makedirs(self.cache, exist_ok=True)
        self._client = None

    def _cloud(self):
        if self._client is not None:
            return self._client
        try:
            from cloud_sync import WebDavClient, load_config
            cfg = load_config()
            if not cfg.get("user") or not cfg.get("password"):
                return None
            base = (cfg.get("remote_dir") or "BasaProject").strip("/")
            self.remote_dir = f"{base}/mail/att"
            c = WebDavClient(cfg["url"], cfg["user"], cfg["password"],
                             timeout=300, retries=3, log=self.log)
            c.ensure_dir(f"{base}/mail")
            c.ensure_dir(self.remote_dir)
            self._client = c
            return c
        except Exception as e:
            self.log(f"[att] облако недоступно: {e}")
            return None

    def store(self, msg_id, files, upload=True):
        saved = 0
        for f in files:
            data = f.get("data") or b""
            if not data:
                self.db.add_attachment(msg_id, f["name"], "", f.get("size", 0), f.get("mime", ""))
                continue
            digest = hashlib.sha256(data).hexdigest()
            ext = os.path.splitext(f["name"])[1][:10]
            local = os.path.join(self.cache, digest + ext)
            if not os.path.exists(local):
                with open(local, "wb") as fh:
                    fh.write(data)
            remote = ""
            if upload:
                c = self._cloud()
                if c is not None:
                    remote = f"{self.remote_dir}/{digest}{ext}"
                    try:
                        if c.head(remote) is None:
                            c.put(remote, local)
                    except Exception as e:
                        self.log(f"[att] выгрузка {f['name']}: {e}")
                        remote = ""
            self.db.add_attachment(msg_id, f["name"], digest, len(data), f.get("mime", ""), remote)
            row = self.db.conn.execute(
                "SELECT id FROM attachments WHERE msg_id=? AND name=?", (msg_id, f["name"])).fetchone()
            if row:
                self.db.set_attachment_local(row["id"], local)
            saved += 1
        return saved

    def ensure_local(self, att):
        """Ленивое скачивание из облака, если локального файла нет."""
        local = att["local_path"] or ""
        if local and os.path.exists(local):
            return local
        if not att["remote_path"]:
            return ""
        c = self._cloud()
        if c is None:
            return ""
        ext = os.path.splitext(att["name"])[1][:10]
        dst = os.path.join(self.cache, (att["sha256"] or "att") + ext)
        try:
            c.get(att["remote_path"], dst)
            self.db.set_attachment_local(att["id"], dst)
            return dst
        except Exception as e:
            self.log(f"[att] скачивание: {e}")
            return ""
