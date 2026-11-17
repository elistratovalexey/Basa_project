package com.elistratov.basaproject

import android.content.Context
import okhttp3.*
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class DatabaseSyncManager(private val context: Context) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
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

        val credential = Credentials.basic(login, password)
        val fullUrl = webdavUrl.trimEnd('/') + remotePath

        val request = Request.Builder().url(fullUrl).header("Authorization", credential).build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: java.io.IOException) {
                onComplete(false, "Ошибка сети: ${e.message}")
            }
            override fun onResponse(call: Call, response: Response) {
                if (response.isSuccessful && response.body != null) {
                    try {
                        val dbFile = context.getDatabasePath("projects.db")
                        dbFile.parentFile?.mkdirs()
                        FileOutputStream(dbFile).use { fos -> fos.write(response.body!!.bytes()) }
                        onComplete(true, "База данных успешно обновлена из облака")
                    } catch (e: Exception) {
                        onComplete(false, "Ошибка записи файла: ${e.message}")
                    }
                } else {
                    onComplete(false, "Ошибка загрузки: ${response.code}. Проверьте путь и пароль.")
                }
            }
        })
    }
}