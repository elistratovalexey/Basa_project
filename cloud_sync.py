# -*- coding: utf-8 -*-
"""Умная синхронизация SQLite-базы с облаком Mail.ru по WebDAV.

Живая БД не отдаётся в облако напрямую: снимок через VACUUM INTO / backup API,
сжатие gzip, загрузка по WebDAV. Перед загрузкой — проверка ETag, скачивание
чужой версии и трёхстороннее слияние по строкам.
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


class WebDavError(Exception):
    pass


# ==================================================================
# WebDAV-клиент
# ==================================================================
class WebDavClient:
    def __init__(self, base_url, user, password, timeout=300, retries=4, log=None):
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.user = user
        self.password = password
        self.timeout = int(timeout or 300)
        self.retries = max(1, int(retries or 4))
        self.log = log or (lambda m: None)
        self._dirs_ok = set()

    def _url(self, path):
        parts = [urllib.parse.quote(p) for p in path.strip("/").split("/") if p]
        return self.base_url + "/" + "/".join(parts)

    def _retry(self, desc, fn):
        """Повтор при таймаутах/сетевых сбоях. Ошибки 4xx (кроме 408/429) не повторяем."""
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                return fn()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (401, 403):
                    raise WebDavError(f"{desc}: доступ запрещён ({e.code}) — "
                                      f"проверьте логин и пароль приложения") from e
                if e.code == 412:
                    raise WebDavError("REMOTE_CHANGED") from e
                if e.code == 405:
                    raise WebDavError(f"{desc}: HTTP 405 (уже существует)") from e
                if 400 <= e.code < 500 and e.code not in (408, 429):
                    raise WebDavError(f"{desc}: HTTP {e.code} {e.reason}") from e
                last = WebDavError(f"{desc}: HTTP {e.code} {e.reason}")
            except (TimeoutError, socket.timeout):
                last = WebDavError(f"{desc}: таймаут {self.timeout} с")
            except urllib.error.URLError as e:
                reason = getattr(e, "reason", e)
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    last = WebDavError(f"{desc}: таймаут {self.timeout} с")
                else:
                    last = WebDavError(f"{desc}: сеть недоступна ({reason})")
            except OSError as e:
                last = WebDavError(f"{desc}: сетевая ошибка ({e})")
            if attempt < self.retries:
                pause = 2 * attempt
                self.log(f"{desc}: попытка {attempt}/{self.retries} не удалась, "
                         f"повтор через {pause} с…")
                time.sleep(pause)
        raise last

    def _request(self, method, path, data=None, headers=None):
        def call():
            req = urllib.request.Request(self._url(path), data=data, method=method)
            token = base64.b64encode(f"{self.user}:{self.password}".encode()).decode()
            req.add_header("Authorization", "Basic " + token)
            req.add_header("User-Agent", "BasaProject-Sync/1.2")
            req.add_header("Connection", "close")
            for k, v in (headers or {}).items():
                req.add_header(k, v)
            return urllib.request.urlopen(req, timeout=self.timeout)
        return self._retry(f"{method} {path}", call)

    def ensure_dir(self, path):
        parts = [p for p in path.strip("/").split("/") if p]
        for i in range(len(parts)):
            sub = "/".join(parts[:i + 1])
            if sub in self._dirs_ok:
                continue
            try:
                self._request("MKCOL", sub)
            except WebDavError as e:
                if "405" not in str(e) and "409" not in str(e):
                    raise
            self._dirs_ok.add(sub)

    def head(self, path):
        r = self._request("HEAD", path)
        if r is None:
            return None
        h = r.headers
        try:
            size = int(h.get("Content-Length") or 0)
        except ValueError:
            size = 0
        return {"etag": (h.get("ETag") or "").strip('"'),
                "size": size, "modified": h.get("Last-Modified") or ""}

    def get(self, path, dest_file):
        def call():
            r = self._request("GET", path)
            if r is None:
                return None
            total = 0
            with open(dest_file, "wb") as f:
                while True:
                    chunk = r.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
                    if total % (5 * 1024 * 1024) < 1024 * 1024:
                        self.log(f"GET {path}: скачано {total // 1048576} МБ…")
            return (r.headers.get("ETag") or "").strip('"')
        return self._retry(f"чтение {path}", call)

    def put(self, path, src_file, if_match=None):
        size = os.path.getsize(src_file)
        with open(src_file, "rb") as f:
            data = f.read()
        headers = {"Content-Type": "application/octet-stream",
                   "Content-Length": str(size)}
        if if_match:
            headers["If-Match"] = f'"{if_match}"'
        self.log(f"PUT {path}: отправка {size / 1048576:.1f} МБ…")
        r = self._request("PUT", path, data=data, headers=headers)
        return (r.headers.get("ETag") or "").strip('"') if r is not None else ""

    def delete(self, path):
        self._request("DELETE", path)

    def list_dir(self, path):
        body = ('<?xml version="1.0"?><propfind xmlns="DAV:">'
                '<prop><getetag/><getcontentlength/><resourcetype/></prop></propfind>')

        def call():
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
        return self._retry(f"список {path}", call)


# ==================================================================
# Конфигурация и состояние
# ==================================================================
# ==================================================================
# Конфигурация: ЕДИНЫЙ источник — настройки синхронизации из окна «Облако»
# ==================================================================
DEFAULT_CONFIG = {
    "url": DEFAULT_URL,
    "user": "",
    "password": "",
    "remote_dir": "BasaProject",
    "auto": True,
    "interval_min": 15,
    "debounce_sec": 120,
    "keep_remote": 10,
    "timeout_sec": 300,
    "retries": 4,
    "backup_every_min": 60,
    "encrypt": False,
}


def _config_dirs(app_dir=None):
    """Порядок поиска: папка данных → папка программы → рядом с модулем."""
    dirs = []
    try:
        from paths import CONFIG_DIR, DATA_DIR, INSTALL_DIR
        for d in (CONFIG_DIR, DATA_DIR, INSTALL_DIR):
            if d and d not in dirs:
                dirs.append(d)
    except Exception:
        pass
    if app_dir and app_dir not in dirs:
        dirs.append(app_dir)
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in dirs:
        dirs.append(here)
    return dirs


def config_file_path(app_dir=None, for_write=False):
    dirs = _config_dirs(app_dir)
    if for_write:
        return os.path.join(dirs[0], "cloud_config.json")
    for d in dirs:
        p = os.path.join(d, "cloud_config.json")
        if os.path.isfile(p):
            return p
    return os.path.join(dirs[0], "cloud_config.json")


def load_config(app_dir=None):
    """Настройки синхронизации (cloud_config.json).
    Переменные окружения ПЕРЕОПРЕДЕЛЯЮТ файл — это нужно для CI/секретов."""
    cfg = dict(DEFAULT_CONFIG)
    path = config_file_path(app_dir)
    source = "значения по умолчанию"
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update({k: v for k, v in data.items()
                            if v not in (None, "") and not k.startswith("_")})
            source = f"настройки синхронизации: {path}"
        except Exception as e:
            print(f"[cloud] конфиг не прочитан ({path}): {e}")

    env_user = os.environ.get("MAILRU_USER")
    env_pass = os.environ.get("MAILRU_APP_PASSWORD")
    env_url = os.environ.get("MAILRU_WEBDAV_URL")
    env_dir = os.environ.get("MAILRU_REMOTE_DIR")
    if env_user:
        cfg["user"] = env_user
    if env_pass:
        cfg["password"] = env_pass
    if env_url:
        cfg["url"] = env_url
    if env_dir:
        cfg["remote_dir"] = env_dir
    if env_user or env_pass:
        source = "переменные окружения (MAILRU_USER / MAILRU_APP_PASSWORD)"

    cfg["_source"] = source
    cfg["_config_file"] = path
    return cfg


def save_config(app_dir=None, cfg=None):
    """Сохраняет настройки в папку ДАННЫХ (переживает переустановку)."""
    cfg = cfg or {}
    path = config_file_path(app_dir, for_write=True)
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def credentials_info(app_dir=None):
    """Для диагностики: откуда взяты логин/пароль (пароль не показываем)."""
    cfg = load_config(app_dir)
    return {"user": cfg.get("user") or "—",
            "url": cfg.get("url"),
            "remote_dir": cfg.get("remote_dir"),
            "has_password": bool(cfg.get("password")),
            "source": cfg.get("_source"),
            "file": cfg.get("_config_file")}

class SyncState:
    def __init__(self, work_dir):
        self.path = os.path.join(work_dir, "sync_state.json")
        self.data = {"remote_etag": "", "last_sync": "", "last_error": "",
                     "device": socket.gethostname(), "device_id": uuid.uuid4().hex[:8],
                     "last_backup_ts": 0}
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
def make_snapshot(conn, dest_path, compact=True):
    """Консистентный снимок. VACUUM INTO даёт компактный файл (быстрее выгрузка)."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)
    if compact:
        try:
            conn.commit()
            conn.execute("VACUUM INTO ?", (dest_path,))
            return dest_path
        except Exception as e:
            print(f"[sync] VACUUM INTO недоступен ({e}), использую backup API")
            if os.path.exists(dest_path):
                os.remove(dest_path)
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
    "sync_log": ["id"],
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
        out[_key_of(r, cols, keys)] = dict(zip(cols, r))
    return out


def _ts_of(row):
    for c in TS_COLUMNS:
        v = row.get(c)
        if v:
            return str(v)
    return ""


def compute_merge(local_conn, remote_conn, base_conn):
    """Трёхстороннее сравнение → (ops, conflicts)."""
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
                    ops.append({"op": "delete", "table": tbl, "cols": cols,
                                "keys": keys, "key_values": list(k)})
                else:
                    ops.append({"op": "upsert", "table": tbl, "cols": cols,
                                "values": [r[c] for c in cols]})
            elif r == b and l != b:
                continue
            elif l != r:
                conflicts.append({"table": tbl, "key": k, "local": l, "remote": r})
                pick = r if _ts_of(r) > _ts_of(l) else l
                ops.append({"op": "upsert", "table": tbl, "cols": cols,
                            "values": [pick[c] for c in cols]})
    return ops, conflicts


def apply_ops(conn, ops):
    """Применяет операции в живой conn ОДНОЙ транзакцией (только GUI-поток)."""
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
    """Сеть — в рабочем потоке, живая БД — только в GUI-потоке."""

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
            raise WebDavError("Не заданы логин/пароль WebDAV.\n"
                              "Заполните их в «Облако → Подключение» и нажмите «Сохранить».\n"
                              f"Файл настроек: {self.cfg.get('_config_file')}")
        return WebDavClient(self.cfg.get("url"), self.cfg["user"], self.cfg["password"],
                            timeout=self.cfg.get("timeout_sec", 300),
                            retries=self.cfg.get("retries", 4),
                            log=self.log)
    # ---------- GUI-поток ----------
    def prepare(self):
        ensure_sync_tables(self.conn)
        make_snapshot(self.conn, self.snap_local)
        return file_sha(self.snap_local)

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

    # ---------- рабочий поток ----------
    def worker(self, local_hash):
        c = self.client()
        c.ensure_dir(self.remote_dir)
        c.ensure_dir(self.rpath("backups"))
        result = {"ops": [], "conflicts": [], "push": False, "message": ""}

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
            meta = c.head(self.rpath("projects.db.gz"))
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
                bc = None
                lc = None
                try:
                    if os.path.exists(self.snap_base):
                        bc = sqlite3.connect(self.snap_base)
                        bc.row_factory = sqlite3.Row
                    lc = sqlite3.connect(self.snap_local)
                    lc.row_factory = sqlite3.Row
                    ops, conflicts = compute_merge(lc, rc, bc)
                    result["ops"], result["conflicts"] = ops, conflicts
                finally:
                    for conn in (lc, bc, rc):
                        if conn is not None:
                            try:
                                conn.close()
                            except Exception:
                                pass

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

    def publish(self, snapshot_path):
        c = self.client()
        gz = os.path.join(self.work, "upload.db.gz")
        gzip_file(snapshot_path, gz)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        every = int(self.cfg.get("backup_every_min", 60) or 0)
        last_bk = float(self.state.data.get("last_backup_ts", 0) or 0)
        if every <= 0 or (time.time() - last_bk) >= every * 60:
            c.put(self.rpath(f"backups/projects_{stamp}.db.gz"), gz)
            self.state.data["last_backup_ts"] = time.time()
            self._rotate(c)

        etag = c.put(self.rpath("projects.db.gz"), gz,
                     if_match=self.state.data.get("remote_etag") or None)
        self.state.data["remote_etag"] = etag
        self.state.data["last_sync"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        self.state.data["last_error"] = ""
        self.state.save()
        shutil.copyfile(snapshot_path, self.snap_base)
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