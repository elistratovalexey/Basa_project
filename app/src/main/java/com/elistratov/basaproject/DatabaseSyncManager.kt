package com.elistratov.basaproject

import android.content.Context
import okhttp3.*
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPInputStream

class DatabaseSyncManager(private val context: Context) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    fun syncDatabase(onComplete: (Boolean, String) -> Unit) {
        val prefs = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
        val webdavUrl = prefs.getString("webdav_url", "https://webdav.cloud.mail.ru/") ?: "https://webdav.cloud.mail.ru/"
        val login = prefs.getString("webdav_login", "") ?: ""
        val password = prefs.getString("webdav_password", "") ?: ""
        val remotePath = prefs.getString("remote_db_path", "/projects.db") ?: "/projects.db"

        if (login.isEmpty() || password.isEmpty()) {
            onComplete(false, "Не настроены логин или пароль WebDAV в настройках")
            return
        }
        val fullUrl = webdavUrl.trimEnd('/') + "/" + remotePath.trimStart('/')
        val request = Request.Builder()
            .url(fullUrl)
            .header("Authorization", Credentials.basic(login, password))
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: java.io.IOException) {
                onComplete(false, "Ошибка сети: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    try {
                        if (!it.isSuccessful) {
                            onComplete(false, "Ошибка загрузки: ${it.code}. Проверьте путь, логин и пароль приложения.")
                            return
                        }
                        var data = it.body?.bytes() ?: ByteArray(0)
                        if (data.size < 100) {
                            onComplete(false, "Скачан пустой файл. Проверьте путь к базе в облаке.")
                            return
                        }
                        // .gz-копия из облака (Python выгружает projects_*.db.gz) — распаковываем
                        if (data[0] == 0x1f.toByte() && data[1] == 0x8b.toByte()) {
                            data = GZIPInputStream(data.inputStream()).use { gz -> gz.readBytes() }
                        }
                        // защита: это настоящая база SQLite, а не HTML-страница ошибки?
                        if (String(data, 0, 16, Charsets.US_ASCII) != "SQLite format 3\u0000") {
                            onComplete(false, "По этому пути НЕ база SQLite. Укажите путь к файлу .db или .db.gz")
                            return
                        }
                        val dbFile = context.getDatabasePath("projects.db")
                        dbFile.parentFile?.mkdirs()
                        val tmp = File(dbFile.parentFile, "projects.db.tmp")
                        tmp.writeBytes(data)
                        File(dbFile.path + "-wal").delete()
                        File(dbFile.path + "-shm").delete()
                        if (dbFile.exists()) dbFile.delete()
                        if (!tmp.renameTo(dbFile)) {
                            onComplete(false, "Не удалось сохранить базу на устройстве")
                            return
                        }
                        onComplete(true, "База обновлена: ${data.size / 1024} КБ")
                    } catch (e: Exception) {
                        onComplete(false, "Ошибка: ${e.message}")
                    }
                }
            }
        })
    }
}