# -*- coding: utf-8 -*-
"""Умная синхронизация SQLite-базы с облаком Mail.ru по WebDAV.

Живая БД не копируется напрямую: снимок через sqlite3 backup API,
сжатие gzip, загрузка по WebDAV. Перед загрузкой — проверка ETag,
скачивание чужой версии и трёхстороннее слияние по строкам.
"""
import base64
import gzip
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime

DAV_NS = "{DAV:}"
DEFAULT_URL = "https://webdav.cloud.mail.ru"


# ==================================================================
# WebDAV-клиент
# ==================================================================
class WebDavError(Exception):
    pass


class WebDavClient:
    def __init__(self, base_url, user, password, timeout=45):
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.user = user
        self.password = password
        self.timeout = timeout

    def _url(self, path):
        parts = [urllib.parse.quote(p) for p in path.strip("/").split("/") if p]
        return self.base_url + "/" + "/".join(parts)

    def _request(self, method, path, data=None, headers=None):
        req = urllib.request.Request(self._url(path), data=data, method=method)
        token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
        req.add_header("Authorization", "Basic " + token)
        req.add_header("User-Agent", "BasaProject-Sync/1.0")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise WebDavError(f"{method} {path} → HTTP {e.code} {e.reason}") from e
        except urllib.error.URLError as e:
            raise WebDavError(f"{method} {path} → сеть недоступна: {e.reason}") from e

    def ensure_dir(self, path):
        """Создаёт коллекцию и всех родителей (MKCOL идемпотентен)."""
        parts = [p for p in path.strip("/").split("/") if p]
        for i in range(len(parts)):
            sub = "/".join(parts[:i + 1])
            try:
                self._request("MKCOL", sub)
            except WebDavError as e:
                if "405" not in str(e) and "409" not in str(e):
                    raise

    def head(self, path):
        """→ {'etag', 'size', 'modified'} или None."""
        r = self._request("HEAD", path)
        if r is None:
            return None
        h = r.headers
        try:
            size = int(h.get("Content-Length") or 0)
        except ValueError:
            size = 0
        return {"etag": (h.get("ETag") or "").strip('"'),
                "size": size,
                "modified": h.get("Last-Modified") or ""}

    def get(self, path, dest_file):
        r = self._request("GET", path)
        if r is None:
            return None
        with open(dest_file, "wb") as f:
            shutil.copyfileobj(r, f)
        return (r.headers.get("ETag") or "").strip('"')

    def put(self, path, src_file, if_match=None):
        with open(src_file, "rb") as f:
            data = f.read()
        headers = {"Content-Type": "application/octet-stream"}
        if if_match:
            headers["If-Match"] = f'"{if_match}"'
        try:
            r = self._request("PUT", path, data=data, headers=headers)
        except WebDavError as e:
            if "412" in str(e):
                raise WebDavError("REMOTE_CHANGED") from e
            raise
        return (r.headers.get("ETag") or "").strip('"') if r is not None else ""

    def delete(self, path):
        self._request("DELETE", path)

    def list_dir(self, path):
        body = ('<?xml version="1.0"?><propfind xmlns="DAV:">'
                '<prop><getetag/><getcontentlength/><resourcetype/></prop></propfind>')
        r = self._request("PROPFIND", path, data=body.encode(),
                          headers={"Depth": "1", "Content-Type": "application/xml"})
        if r is None:
            return []
        root = ET.fromstring(r.read())
        out = []
        for resp in root.findall(f"{DAV_NS}response"):
            href = resp.findtext(f"{DAV_NS}href") or ""
            name = urllib.parse.unquote(href.rstrip("/").split("/")[-1])
            is_dir = resp.find(f".//{DAV_NS}collection") is not None
            prop = resp.find(f".//{DAV_NS}prop")
            etag = (prop.findtext(f"{DAV_NS}getetag") or "").strip('"') if prop is not None else ""
            try:
                size = int(prop.findtext(f"{DAV_NS}getcontentlength") or 0) if prop is not None else 0
            except ValueError:
                size = 0
            if name and not is_dir:
                out.append({"name": name, "etag": etag, "size": size})
        return out


# ==================================================================
# Конфигурация и состояние
# ==================================================================
def load_config(app_dir):
    """Приоритет: переменные окружения → cloud_config.json."""
    cfg = {
        "url": os.environ.get("MAILRU_WEBDAV_URL", DEFAULT_URL),
        "user": os.environ.get("MAILRU_USER", ""),
        "password": os.environ.get("MAILRU_APP_PASSWORD", ""),
        "remote_dir": "BasaProject",
        "auto": True,
        "interval_min": 15,
        "debounce_sec": 45,
        "keep_remote": 10,
        "encrypt": False,
    }
    path = os.path.join(app_dir, "cloud_config.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[sync] конфиг не прочитан: {e}")
    return cfg


def save_config(app_dir, cfg):
    path = os.path.join(app_dir, "cloud_config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class SyncState:
    def __init__(self, work_dir):
        self.path = os.path.join(work_dir, "sync_state.json")
        self.data = {"remote_etag": "", "last_sync": "", "last_error": "",
                     "device": socket.gethostname(), "device_id": uuid.uuid4().hex[:8]}
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except Exception:
                pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)


# ==================================================================
# Снимки и хэши
# ==================================================================
def make_snapshot(conn, dest_path):
    """Консистентный снимок живой БД (безопасно при открытых транзакциях)."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    dst = sqlite3.connect(dest_path)
    try:
        conn.backup(dst)
    finally:
        dst.close()
    return dest_path


def file_sha(path):
    if not path or not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gzip_file(src, dst):
    with open(src, "rb") as fi, gzip.open(dst, "wb", compresslevel=6) as fo:
        shutil.copyfileobj(fi, fo)
    return dst


def gunzip_file(src, dst):
    with gzip.open(src, "rb") as fi, open(dst, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return dst


# ==================================================================
# Слияние по строкам
# ==================================================================
SKIP_TABLES = {"sqlite_sequence", "sqlite_stat1"}

KEY_COLUMNS = {
    "projects": ["name"],
    "payments": ["project_id", "number"],
    "specifications": ["project_id", "number"],
    "purchases": ["project_id", "number"],
    "orders": ["id"],
    "order_items": ["id"],
    "nomenclature": ["id"],
    "nomenclature_aliases": ["alias_norm"],
    "manufacturers": ["name"],
    "suppliers": ["name"],
    "subprojects": ["name", "project_name"],
    "kd_directory": ["kd_number", "project_name"],
    "delivery_addresses": ["name"],
    "purchase_specifications": ["id"],
    "purchase_spec_items": ["id"],
    "purchase_payments": ["id"],
    "price_history": ["id"],
    "currency_rates": ["date", "code"],
    "work_types": ["name"],
    "work_statuses": ["name"],
    "plan_fact": ["project_id", "number"],
    "sync_tombstones": ["tbl", "row_key"],
}

TS_COLUMNS = ("updated_at", "receipt_date", "order_date", "date",
              "payment_date", "ts", "contract_date")


def ensure_sync_tables(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS sync_tombstones (
        tbl TEXT NOT NULL,
        row_key TEXT NOT NULL,
        ts TEXT NOT NULL,
        device TEXT DEFAULT '',
        PRIMARY KEY (tbl, row_key))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, device TEXT, action TEXT, details TEXT)''')
    conn.commit()


def mark_deleted(conn, tbl, key_dict):
    """Регистрирует удаление, чтобы оно не «воскресло» при слиянии."""
    ensure_sync_tables(conn)
    conn.execute("INSERT OR REPLACE INTO sync_tombstones (tbl, row_key, ts, device) "
                 "VALUES (?, ?, ?, ?)",
                 (tbl, json.dumps(key_dict, sort_keys=True, ensure_ascii=False),
                  datetime.now().isoformat(timespec="seconds"), socket.gethostname()))
    conn.commit()


def _tables(conn):
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        if r[0] not in SKIP_TABLES]


def _cols(conn, tbl):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({tbl})")]


def _norm(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _key_of(row, cols, keys):
    return tuple(_norm(row[cols.index(k)]) for k in keys)


def _read_table(conn, tbl, cols, keys):
    out = {}
    for r in conn.execute(f"SELECT {', '.join(cols)} FROM {tbl}"):
        d = dict(zip(cols, r))
        out[_key_of(r, cols, keys)] = d
    return out


def _ts_of(row):
    for c in TS_COLUMNS:
        v = row.get(c)
        if v:
            return str(v)
    return ""


def compute_merge(local_conn, remote_conn, base_conn):
    """Трёхстороннее сравнение. Возвращает (ops, conflicts).

    ops: [{'op': 'upsert'|'delete', 'table', 'cols', 'values'|'keys'}]
    conflictos: список словарей с описанием спорных строк.
    """
    ops, conflicts = [], []
    lt, rt = set(_tables(local_conn)), set(_tables(remote_conn))
    for tbl in sorted(lt & rt):
        lc, rc = _cols(local_conn, tbl), _cols(remote_conn, tbl)
        cols = [c for c in lc if c in rc]
        keys = [k for k in KEY_COLUMNS.get(tbl, ["id"]) if k in cols]
        if not keys:
            continue
        L = _read_table(local_conn, tbl, cols, keys)
        R = _read_table(remote_conn, tbl, cols, keys)
        B = _read_table(base_conn, tbl, cols, keys) if base_conn is not None else {}

        for k in sorted(set(L) | set(R), key=lambda x: tuple(map(str, x))):
            l, r, b = L.get(k), R.get(k), B.get(k)
            if l is not None and r is not None and l == r:
                continue
            if b is None:
                if l is None:
                    ops.append({"op": "upsert", "table": tbl, "cols": cols,
                                "values": [r[c] for c in cols]})
                elif r is None:
                    ops.append({"op": "upsert", "table": tbl, "cols": cols,
                                "values": [l[c] for c in cols]})
                else:
                    conflicts.append({"table": tbl, "key": k, "local": l, "remote": r})
                    pick = r if _ts_of(r) > _ts_of(l) else l
                    ops.append({"op": "upsert", "table": tbl, "cols": cols,
                                "values": [pick[c] for c in cols]})
                continue
            if l == b and r != b:
                if r is None:
                    ops.append({"op": "delete", "table": tbl, "cols": cols, "keys": keys,
                                "key_values": list(k)})
                else:
                    ops.append({"op": "upsert", "table": tbl, "cols": cols,
                                "values": [r[c] for c in cols]})
            elif r == b and l != b:
                continue  # локаль уже новее — оставляем как есть
            elif l != r:
                conflicts.append({"table": tbl, "key": k, "local": l, "remote": r})
                pick = r if _ts_of(r) > _ts_of(l) else l
                ops.append({"op": "upsert", "table": tbl, "cols": cols,
                            "values": [pick[c] for c in cols]})
    return ops, conflicts


def apply_ops(conn, ops):
    """Применяет операции в живойconn ОДНОЙ транзакцией (вызывать из GUI-потока)."""
    if not ops:
        return 0
    with conn:
        for o in ops:
            tbl, cols = o["table"], o["cols"]
            if o["op"] == "upsert":
                ph = ", ".join("?" for _ in cols)
                conn.execute(f"INSERT OR REPLACE INTO {tbl} ({', '.join(cols)}) VALUES ({ph})",
                             o["values"])
            else:
                where = " AND ".join(f"{k}=?" for k in o["keys"])
                conn.execute(f"DELETE FROM {tbl} WHERE {where}", o["key_values"])
    return len(ops)


# ==================================================================
# Менеджер синхронизации
# ==================================================================
class SyncManager:
    """Оркестратор. Сеть — в рабочем потоке, живая БД — только в GUI-потоке."""

    def __init__(self, app_dir, db_path, conn, log=print):
        self.app_dir = app_dir
        self.db_path = db_path
        self.conn = conn
        self.log = log
        self.work = os.path.join(app_dir, "cloud_sync")
        os.makedirs(self.work, exist_ok=True)
        self.state = SyncState(self.work)
        self.cfg = load_config(app_dir)
        self.busy = False

    # ---------- пути ----------
    @property
    def remote_dir(self):
        return self.cfg.get("remote_dir", "BasaProject").strip("/")

    def rpath(self, name):
        return f"{self.remote_dir}/{name}"

    @property
    def snap_local(self):
        return os.path.join(self.work, "local_snapshot.db")

    @property
    def snap_base(self):
        return os.path.join(self.work, "base_snapshot.db")

    @property
    def snap_remote(self):
        return os.path.join(self.work, "remote_snapshot.db")

    def client(self):
        if not self.cfg.get("user") or not self.cfg.get("password"):
            raise WebDavError("Не заданы логин/пароль WebDAV (Настройки → Облако)")
        return WebDavClient(self.cfg.get("url"), self.cfg["user"], self.cfg["password"])

    # ---------- подготовка (GUI-поток) ----------
    def prepare(self):
        ensure_sync_tables(self.conn)
        make_snapshot(self.conn, self.snap_local)
        return file_sha(self.snap_local)

    # ---------- сеть + сравнение (рабочий поток) ----------
    def worker(self, local_hash):
        c = self.client()
        c.ensure_dir(self.remote_dir)
        c.ensure_dir(self.rpath("backups"))
        result = {"ops": [], "conflicts": [], "push": False, "message": ""}

        # 1. Лок: другая машина сейчас синхронизируется?
        lock_name = self.rpath("sync.lock")
        lock_tmp = os.path.join(self.work, "lock.json")
        if c.get(lock_name, lock_tmp):
            try:
                with open(lock_tmp, "r", encoding="utf-8") as f:
                    lk = json.load(f)
                age = time.time() - float(lk.get("ts", 0))
                if lk.get("device_id") != self.state.data["device_id"] and age < 300:
                    result["message"] = (f"Занято: {lk.get('device')} синхронизируется "
                                         f"{int(age)} с назад. Повторите позже.")
                    return result
            except Exception:
                pass
        with open(lock_tmp, "w", encoding="utf-8") as f:
            json.dump({"device": self.state.data["device"],
                       "device_id": self.state.data["device_id"], "ts": time.time()}, f)
        c.put(lock_name, lock_tmp)

        try:
            # 2. Что в облаке?
            meta = c.head(self.rpath("projects.db.gz"))
            base_conn = None
            if meta:
                known = self.state.data.get("remote_etag", "")
                if meta["etag"] != known or not os.path.exists(self.snap_remote):
                    gz = os.path.join(self.work, "remote.db.gz")
                    etag = c.get(self.rpath("projects.db.gz"), gz)
                    gunzip_file(gz, self.snap_remote)
                    self.state.data["remote_etag"] = etag or meta["etag"]
                    result["message"] += "Скачана свежая версия из облака. "

                rc = sqlite3.connect(self.snap_remote)
                rc.row_factory = sqlite3.Row
                try:
                    if os.path.exists(self.snap_base):
                        bc = sqlite3.connect(self.snap_base)
                        bc.row_factory = sqlite3.Row
                        base_conn = bc
                    lc = sqlite3.connect(self.snap_local)
                    lc.row_factory = sqlite3.Row
                    try:
                        ops, conflicts = compute_merge(lc, rc, base_conn)
                        result["ops"], result["conflicts"] = ops, conflicts
                    finally:
                        lc.close()
                        if base_conn:
                            base_conn.close()
                finally:
                    rc.close()

            local_changed = local_hash != file_sha(self.snap_base)
            result["push"] = bool(local_changed or result["ops"] or not meta)
            if not result["push"]:
                result["message"] += "Изменений нет — облако актуально."
            return result
        finally:
            try:
                c.delete(lock_name)
            except Exception:
                pass

    # ---------- публикация снимка (рабочий поток, после apply_ops) ----------
    def publish(self, snapshot_path):
        c = self.client()
        gz = os.path.join(self.work, "upload.db.gz")
        gzip_file(snapshot_path, gz)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        c.put(self.rpath(f"backups/projects_{stamp}.db.gz"), gz)
        etag = c.put(self.rpath("projects.db.gz"), gz,
                     if_match=self.state.data.get("remote_etag") or None)
        self.state.data["remote_etag"] = etag
        self.state.data["last_sync"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.state.data["last_error"] = ""
        self.state.save()
        shutil.copyfile(snapshot_path, self.snap_base)
        self._rotate(c)
        return stamp

    def _rotate(self, c):
        keep = int(self.cfg.get("keep_remote", 10) or 10)
        try:
            files = [f for f in c.list_dir(self.rpath("backups"))
                     if f["name"].startswith("projects_")]
            files.sort(key=lambda f: f["name"])
            for old in files[:-keep] if keep > 0 else []:
                c.delete(self.rpath("backups/" + old["name"]))
        except Exception as e:
            self.log(f"[sync] ротация копий: {e}")

    # ---------- аварийная копия перед применением ----------
    def safety_backup(self):
        d = os.path.join(self.app_dir, "backups")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "presync_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
        make_snapshot(self.conn, p)
        return p

    def log_sync(self, action, details=""):
        try:
            self.conn.execute("INSERT INTO sync_log (ts, device, action, details) VALUES (?,?,?,?)",
                              (datetime.now().isoformat(timespec="seconds"),
                               self.state.data["device"], action, details))
            self.conn.commit()
        except Exception:
            pass