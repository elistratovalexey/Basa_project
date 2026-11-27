package com.elistratov.basaproject

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.os.Handler
import android.os.Looper
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPInputStream
import java.util.zip.GZIPOutputStream

object CloudPush {

    fun pushWarehouse(context: Context, onResult: (Boolean, String) -> Unit) {
        val main = Handler(Looper.getMainLooper())
        fun post(ok: Boolean, msg: String) = main.post { onResult(ok, msg) }
        Thread {
            try {
                val prefs = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
                val url = prefs.getString("webdav_url", "https://webdav.cloud.mail.ru/") ?: "https://webdav.cloud.mail.ru/"
                val login = prefs.getString("webdav_login", "") ?: ""
                val pass = prefs.getString("webdav_password", "") ?: ""
                val remote = prefs.getString("remote_db_path", "/BasaProject/projects.db") ?: "/BasaProject/projects.db"
                if (login.isEmpty() || pass.isEmpty()) { post(false, "Облако не настроено — сохранено только локально"); return@Thread }
                val client = OkHttpClient.Builder().connectTimeout(30, TimeUnit.SECONDS)
                    .readTimeout(180, TimeUnit.SECONDS).writeTimeout(180, TimeUnit.SECONDS).build()
                val cred = Credentials.basic(login, pass)
                val full = url.trimEnd('/') + "/" + remote.trimStart('/')

                var data = ByteArray(0)
                client.newCall(Request.Builder().url(full).header("Authorization", cred).build()).execute().use { r ->
                    if (r.isSuccessful) data = r.body?.bytes() ?: ByteArray(0)
                }
                if (data.size > 2 && data[0] == 0x1f.toByte() && data[1] == 0x8b.toByte())
                    data = GZIPInputStream(data.inputStream()).use { it.readBytes() }
                val tmp = File(context.cacheDir, "cloud_merge.db")
                if (data.size >= 100 && String(data, 0, 16, Charsets.US_ASCII) == "SQLite format 3\u0000") tmp.writeBytes(data)
                else tmp.writeBytes(context.getDatabasePath("projects.db").readBytes())

                val local = SQLiteDatabase.openDatabase(context.getDatabasePath("projects.db").absolutePath, null, SQLiteDatabase.OPEN_READONLY)
                val cloud = SQLiteDatabase.openDatabase(tmp.absolutePath, null, SQLiteDatabase.OPEN_READWRITE)
                cloud.execSQL("CREATE TABLE IF NOT EXISTS storage_cells (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, barcode TEXT UNIQUE, note TEXT DEFAULT '')")
                cloud.execSQL("CREATE TABLE IF NOT EXISTS warehouse_names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, article TEXT DEFAULT '', unit TEXT DEFAULT 'шт', note TEXT DEFAULT '')")
                cloud.execSQL("CREATE TABLE IF NOT EXISTS warehouse_items (id INTEGER PRIMARY KEY AUTOINCREMENT, cell_id INTEGER DEFAULT 0, name TEXT DEFAULT '', qty REAL DEFAULT 0, description TEXT DEFAULT '', updated_at TEXT DEFAULT '')")
                ensureCol(cloud, "warehouse_items", "barcode")
                copy(local, cloud, "storage_cells", arrayOf("id", "code", "barcode", "note"))
                copy(local, cloud, "warehouse_names", arrayOf("id", "name", "article", "unit", "note"))
                mergeItems(local, cloud)
                cloud.close(); local.close()

                var out = tmp.readBytes()
                if (remote.endsWith(".gz")) {
                    val bo = ByteArrayOutputStream(); GZIPOutputStream(bo).use { it.write(out) }; out = bo.toByteArray()
                }
                val put = Request.Builder().url(full).header("Authorization", cred)
                    .put(out.toRequestBody("application/octet-stream".toMediaType())).build()
                client.newCall(put).execute().use { r ->
                    post(r.isSuccessful, if (r.isSuccessful) "Склад сохранён и выгружен в облако" else "Ошибка выгрузки: ${r.code}")
                }
            } catch (e: Exception) { post(false, "Сохранено локально, облако: ${e.message}") }
        }.start()
    }

    private fun ensureCol(d: SQLiteDatabase, table: String, col: String) {
        var has = false
        d.rawQuery("PRAGMA table_info($table)", null).use { c ->
            while (c.moveToNext()) if (c.getString(1) == col) has = true
        }
        if (!has) d.execSQL("ALTER TABLE $table ADD COLUMN $col TEXT DEFAULT ''")
    }

    private fun hasCol(d: SQLiteDatabase, table: String, col: String): Boolean {
        var has = false
        try {
            d.rawQuery("PRAGMA table_info($table)", null).use { c ->
                while (c.moveToNext()) if (c.getString(1) == col) has = true
            }
        } catch (e: Exception) { }
        return has
    }

    private fun copy(src: SQLiteDatabase, dst: SQLiteDatabase, table: String, cols: Array<String>) {
        try {
            src.rawQuery("SELECT ${cols.joinToString(",")} FROM $table", null).use { c ->
                while (c.moveToNext()) {
                    val vals = Array<Any?>(cols.size) { i -> if (c.isNull(i)) null else c.getString(i) }
                    dst.execSQL("INSERT OR REPLACE INTO $table (${cols.joinToString(",")}) VALUES (${cols.joinToString(",") { "?" }})", vals)
                }
            }
        } catch (e: Exception) { }
    }

    private fun mergeItems(src: SQLiteDatabase, dst: SQLiteDatabase) {
        try {
            val bc = if (hasCol(src, "warehouse_items", "barcode")) "IFNULL(barcode,'')" else "''"
            src.rawQuery("SELECT id, cell_id, name, qty, description, updated_at, $bc FROM warehouse_items", null).use { c ->
                while (c.moveToNext()) {
                    val id = c.getInt(0)
                    val upd = if (c.isNull(5)) "" else c.getString(5)
                    var keep = true
                    dst.rawQuery("SELECT updated_at FROM warehouse_items WHERE id=?", arrayOf(id.toString())).use { d ->
                        if (d.moveToFirst()) {
                            val old = if (d.isNull(0)) "" else d.getString(0)
                            keep = upd >= old
                        }
                    }
                    if (keep) dst.execSQL(
                        "INSERT OR REPLACE INTO warehouse_items (id, cell_id, name, qty, description, updated_at, barcode) VALUES (?,?,?,?,?,?,?)",
                        arrayOf<Any?>(id, c.getInt(1), if (c.isNull(2)) "" else c.getString(2), c.getDouble(3),
                            if (c.isNull(4)) "" else c.getString(4), upd, if (c.isNull(6)) "" else c.getString(6)))
                }
            }
        } catch (e: Exception) { }
    }
}