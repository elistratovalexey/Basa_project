package com.elistratov.basaproject

import android.content.Context
import okhttp3.*
import java.io.File
import java.util.concurrent.TimeUnit
import java.util.zip.GZIPInputStream

class DatabaseSyncManager(private val context: Context) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .build()

    fun syncDatabase(onComplete: (Boolean, String) -> Unit) {
        val prefs = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
        val webdavUrl = prefs.getString("webdav_url", "https://webdav.cloud.mail.ru/") ?: "https://webdav.cloud.mail.ru/"
        val login = prefs.getString("webdav_login", "") ?: ""
        val password = prefs.getString("webdav_password", "") ?: ""
        val remotePath = prefs.getString("remote_db_path", "/BasaProject/projects.db") ?: "/BasaProject/projects.db"

        if (login.isEmpty() || password.isEmpty()) {
            onComplete(false, "Не настроены логин или пароль WebDAV в настройках")
            return
        }
        val credential = Credentials.basic(login, password)
        val fullUrl = webdavUrl.trimEnd('/') + "/" + remotePath.trimStart('/')
        val request = Request.Builder().url(fullUrl).header("Authorization", credential).build()

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
                        if (data.size < 100) { onComplete(false, "Скачан пустой файл. Проверьте путь к базе."); return }
                        if (data[0] == 0x1f.toByte() && data[1] == 0x8b.toByte()) {
                            data = GZIPInputStream(data.inputStream()).use { gz -> gz.readBytes() }
                        }
                        if (String(data, 0, 16, Charsets.US_ASCII) != "SQLite format 3\u0000") {
                            onComplete(false, "По этому пути НЕ база SQLite. Укажите путь к файлу .db или .db.gz")
                            return
                        }
                        writeDb("projects.db", data)
                        val mailMsg = syncMail(prefs, webdavUrl, credential, remotePath)
                        onComplete(true, "База обновлена: ${data.size / 1024} КБ$mailMsg")
                    } catch (e: Exception) {
                        onComplete(false, "Ошибка: ${e.message}")
                    }
                }
            }
        })
    }

    private fun writeDb(name: String, data: ByteArray) {
        val dbFile = context.getDatabasePath(name)
        dbFile.parentFile?.mkdirs()
        val tmp = File(dbFile.parentFile, "$name.tmp")
        tmp.writeBytes(data)
        File(dbFile.path + "-wal").delete()
        File(dbFile.path + "-shm").delete()
        if (dbFile.exists()) dbFile.delete()
        tmp.renameTo(dbFile)
    }

    private fun syncMail(prefs: android.content.SharedPreferences, webdavUrl: String, credential: String, remotePath: String): String {
        return try {
            var dir = "/" + remotePath.trim('/').substringBeforeLast('/', "")
            if (dir.endsWith("/backups")) dir = dir.substringBeforeLast('/', "")
            if (dir == "/" || dir.isEmpty()) dir = "/BasaProject"
            val mailPath = prefs.getString("mail_remote_path", "$dir/mail.db.gz") ?: "$dir/mail.db.gz"
            val url = webdavUrl.trimEnd('/') + "/" + mailPath.trimStart('/')
            val req = Request.Builder().url(url).header("Authorization", credential).build()
            client.newCall(req).execute().use { resp ->
                if (!resp.isSuccessful) return " · переписка: нет в облаке"
                var data = resp.body?.bytes() ?: ByteArray(0)
                if (data.size < 100) return " · переписка: пустой файл"
                if (data[0] == 0x1f.toByte() && data[1] == 0x8b.toByte()) {
                    data = GZIPInputStream(data.inputStream()).use { gz -> gz.readBytes() }
                }
                if (String(data, 0, 16, Charsets.US_ASCII) != "SQLite format 3\u0000") return " · переписка: не база"
                writeDb("mail.db", data)
                " · переписка: ${data.size / 1024} КБ"
            }
        } catch (e: Exception) { " · переписка: ошибка" }
    }
}
