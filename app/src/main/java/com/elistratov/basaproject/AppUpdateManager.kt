package com.elistratov.basaproject

import android.content.Context
import androidx.core.content.pm.PackageInfoCompat
import okhttp3.*
import java.io.File
import java.util.concurrent.TimeUnit

class AppUpdateManager(private val context: Context) {

    enum class Result { UPDATE, CURRENT, ERROR }

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(180, TimeUnit.SECONDS)
        .build()

    fun check(callback: (Result, String, File?) -> Unit) {
        val prefs = context.getSharedPreferences("app_settings", Context.MODE_PRIVATE)
        val url = prefs.getString("webdav_url", "https://webdav.cloud.mail.ru/") ?: "https://webdav.cloud.mail.ru/"
        val login = prefs.getString("webdav_login", "") ?: ""
        val password = prefs.getString("webdav_password", "") ?: ""
        val dir = prefs.getString("apk_remote_dir", "/BasaProject/apk") ?: "/BasaProject/apk"
        if (login.isEmpty() || password.isEmpty()) {
            callback(Result.ERROR, "Сначала настройте облако Mail.ru в ⚙️", null); return
        }
        val base = url.trimEnd('/') + "/" + dir.trim('/')
        val req = Request.Builder().url("$base/BasaProject.apk")
            .header("Authorization", Credentials.basic(login, password)).build()

        client.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: java.io.IOException) {
                callback(Result.ERROR, "Нет связи с облаком: ${e.message}", null)
            }
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    try {
                        if (!it.isSuccessful) {
                            callback(Result.ERROR, "BasaProject.apk не найден в папке (код ${it.code})", null); return
                        }
                        val data = it.body?.bytes() ?: ByteArray(0)
                        if (data.size < 1000 || data[0] != 0x50.toByte() || data[1] != 0x4B.toByte()) {
                            callback(Result.ERROR, "В папке лежит не APK-файл", null); return
                        }
                        val dirF = context.getExternalFilesDir("updates") ?: context.cacheDir
                        dirF.mkdirs()
                        val file = File(dirF, "BasaProject-remote.apk")
                        file.writeBytes(data)
                        val info = context.packageManager.getPackageArchiveInfo(file.absolutePath, 0)
                        if (info == null) { callback(Result.ERROR, "Не удалось прочитать версию APK", null); return }
                        val remote = PackageInfoCompat.getLongVersionCode(info)
                        val current = PackageInfoCompat.getLongVersionCode(
                            context.packageManager.getPackageInfo(context.packageName, 0))
                        if (remote > current) {
                            callback(Result.UPDATE, "Доступна новая версия (сборка $remote, у вас $current)", file)
                        } else {
                            file.delete()
                            callback(Result.CURRENT, "У вас актуальная версия (сборка $current)", null)
                        }
                    } catch (e: Exception) {
                        callback(Result.ERROR, "Ошибка обновления: ${e.message}", null)
                    }
                }
            }
        })
    }
}