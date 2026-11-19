package com.elistratov.basaproject

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.elistratov.basaproject.databinding.ActivitySettingsBinding

class SettingsActivity : AppCompatActivity() {
    private lateinit var binding: ActivitySettingsBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivitySettingsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val prefs = getSharedPreferences("app_settings", MODE_PRIVATE)
        binding.etWebdavUrl.setText(prefs.getString("webdav_url", "https://webdav.cloud.mail.ru/"))
        binding.etLogin.setText(prefs.getString("webdav_login", ""))
        binding.etPassword.setText(prefs.getString("webdav_password", ""))
        binding.etRemotePath.setText(prefs.getString("remote_db_path", "/BasaProject/projects.db"))
        binding.etApkDir.setText(prefs.getString("apk_remote_dir", "/BasaProject/apk"))

        binding.btnSave.setOnClickListener {
            prefs.edit().apply {
                putString("webdav_url", binding.etWebdavUrl.text.toString())
                putString("webdav_login", binding.etLogin.text.toString())
                putString("webdav_password", binding.etPassword.text.toString())
                putString("remote_db_path", binding.etRemotePath.text.toString())
                putString("apk_remote_dir", binding.etApkDir.text.toString())
            }.apply()
            Toast.makeText(this, "Настройки сохранены", Toast.LENGTH_SHORT).show()
        }
    }
}