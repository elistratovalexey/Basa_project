# -*- coding: utf-8 -*-
"""Чтение почты Mail.ru по IMAP: письма, у которых тема содержит название проекта."""
import email
import imaplib
import re
import socket
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime


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
    html = re.sub(r"(?i)</p>", "\n\n", html)
    html = re.sub(r"<[^>]+>", "", html)
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                 ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")):
        html = html.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", html).strip()


def _parts(msg):
    text, html, files = [], [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        name = _dec(part.get_filename() or "")
        disp = (part.get("Content-Disposition") or "").lower()
        if name and ("attachment" in disp or "inline" in disp):
            files.append(name)
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                s = payload.decode(charset, errors="replace")
            except LookupError:
                s = payload.decode("utf-8", errors="replace")
        except Exception:
            continue
        (text if ctype == "text/plain" else html).append(s)
    body = "\n".join(text).strip() or _strip_html("\n".join(html))
    return body, files


class MailClient:
    def __init__(self, cfg, log=print, timeout=60):
        self.cfg = cfg
        self.log = log
        self.timeout = timeout
        self.conn = None

    def connect(self):
        host = self.cfg.get("host") or "imap.mail.ru"
        port = int(self.cfg.get("port") or 993)
        user = (self.cfg.get("email") or "").strip()
        pwd = self.cfg.get("password") or ""
        if not user or not pwd:
            raise MailError("Не заданы e-mail или пароль приложения.\n"
                            "Откройте «Настройка почты».")
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(self.timeout)
        try:
            self.conn = (imaplib.IMAP4_SSL(host, port) if int(self.cfg.get("use_ssl", 1))
                         else imaplib.IMAP4(host, port))
            self.conn.login(user, pwd)
        except imaplib.IMAP4.error as e:
            raise MailError(f"Вход не выполнен: {e}\n"
                            "Для Mail.ru нужен ПАРОЛЬ ДЛЯ ВНЕШНИХ ПРИЛОЖЕНИЙ "
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
                m = re.match(r'\((?P<flags>[^)]*)\)\s+"(?P<delim>[^"]*)"\s+(?P<name>.+)$', s)
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

    def fetch(self, folder, direction, projects, limit=200, progress=None):
        """projects: [{'id':..,'name':..}]. Возвращает список писем для сохранения."""
        self._select(folder)
        typ, data = self.conn.uid("search", None, "ALL")
        if typ != "OK":
            return []
        uids = (data[0] or b"").split()
        uids = uids[-int(limit):]
        found = []
        total = len(uids)
        for i, uid in enumerate(reversed(uids), 1):
            if progress and i % 10 == 0:
                progress(f"{folder}: {i}/{total}")
            try:
                typ, hd = self.conn.uid("fetch", uid,
                                        "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE)])")
                if typ != "OK" or not hd or not isinstance(hd[0], tuple):
                    continue
                head = email.message_from_bytes(hd[0][1])
                subject = _dec(head.get("Subject"))
                low = subject.lower()
                hits = [p for p in projects if p["name"] and p["name"].lower() in low]
                if not hits:
                    continue
                proj = max(hits, key=lambda p: len(p["name"]))
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
                    "folder": folder, "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
                    "message_id": _dec(msg.get("Message-ID")),
                    "subject": subject, "sender": _dec(head.get("From")),
                    "recipients": _dec(head.get("To")), "cc": _dec(head.get("Cc")),
                    "date_sent": date_sent, "date_iso": date_iso,
                    "direction": direction, "body": body,
                    "attachments": "; ".join(files), "size": size,
                })
            except Exception as e:
                self.log(f"[mail] uid {uid}: {e}")
                continue
        return found


def guess_work_type(subject, body, types, default=""):
    """Тип по вхождению названия в тему (приоритет), затем в тело."""
    s = (subject or "").lower()
    for t in types:
        if t and t.lower() in s:
            return t
    b = (body or "").lower()[:4000]
    for t in types:
        if t and t.lower() in b:
            return t
    return default or (types[0] if types else "")
