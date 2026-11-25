# -*- coding: utf-8 -*-
"""Синхронизация mail.db с облаком Mail.ru: pull → merge → push.
Письма append-only, изменённые поля разрешаются по updated_at.
"""
import gzip
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime

from cloud_sync import WebDavClient, WebDavError, load_config


class MailSync:
    def __init__(self, mail_db, app_dir=None, log=print):
        self.db = mail_db
        self.log = log
        self.cfg = load_config(app_dir)
        base = (self.cfg.get("remote_dir") or "BasaProject").strip("/")
        self.remote_dir = base
        self.remote_file = f"{base}/mail.db.gz"
        self.busy = False

    def client(self):
        if not self.cfg.get("user") or not self.cfg.get("password"):
            raise WebDavError("Не заданы логин/пароль облака («☁ Облако → Подключение»).")
        return WebDavClient(self.cfg.get("url"), self.cfg["user"], self.cfg["password"],
                            timeout=max(300, int(self.cfg.get("timeout_sec", 300))),
                            retries=int(self.cfg.get("retries", 4)), log=self.log)

    def _snapshot(self, dest_db):
        """Целостный снимок mail.db через sqlite backup API."""
        dst = sqlite3.connect(dest_db)
        try:
            self.db.conn.backup(dst)
        finally:
            dst.close()

    def sync(self):
        """Возвращает (добавлено, обновлено, выгружено_байт)."""
        if self.busy:
            raise WebDavError("Синхронизация почты уже выполняется")
        self.busy = True
        tmp = tempfile.mkdtemp(prefix="basa_mail_")
        try:
            c = self.client()
            c.ensure_dir(self.remote_dir)
            remote_gz = os.path.join(tmp, "remote.db.gz")
            remote_db = os.path.join(tmp, "remote.db")
            added = updated = 0

            etag = c.get(self.remote_file, remote_gz)
            if etag is not None or os.path.exists(remote_gz):
                self.log("Почта: получен облачный снимок")
                with gzip.open(remote_gz, "rb") as fi, open(remote_db, "wb") as fo:
                    shutil.copyfileobj(fi, fo)
                added, updated = self.db.merge_from(remote_db)
                self.log(f"Почта: слияние — новых {added}, обновлено {updated}")
            else:
                self.log("Почта: облачного снимка ещё нет — создаём")

            local_db = os.path.join(tmp, "local.db")
            self._snapshot(local_db)
            local_gz = os.path.join(tmp, "local.db.gz")
            with open(local_db, "rb") as fi, gzip.open(local_gz, "wb", compresslevel=6) as fo:
                shutil.copyfileobj(fi, fo)
            size = os.path.getsize(local_gz)
            self.log(f"Почта: выгрузка {size / 1048576:.1f} МБ…")
            c.put(self.remote_file, local_gz)

            stamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            self.db.conn.execute("UPDATE mail_settings SET last_sync=? WHERE id=1", (stamp,))
            self.db.conn.commit()
            return added, updated, size
        finally:
            self.busy = False
            shutil.rmtree(tmp, ignore_errors=True)

    def backup_remote(self, keep=5):
        """Копия mail.db.gz в backups/ перед крупными изменениями."""
        try:
            c = self.client()
            c.ensure_dir(f"{self.remote_dir}/backups")
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp = os.path.join(tempfile.gettempdir(), f"mail_{stamp}.db.gz")
            if c.get(self.remote_file, tmp) is None:
                return None
            c.put(f"{self.remote_dir}/backups/mail_{stamp}.db.gz", tmp)
            items = [f for f in c.list_dir(f"{self.remote_dir}/backups")
                     if f["name"].startswith("mail_")]
            items.sort(key=lambda f: f["name"], reverse=True)
            for old in items[keep:]:
                c.delete(f"{self.remote_dir}/backups/{old['name']}")
            return stamp
        except Exception as e:
            self.log(f"Почта: копия не создана — {e}")
            return None
