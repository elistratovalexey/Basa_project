package com.elistratov.basaproject

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.fragment.app.Fragment
import com.elistratov.basaproject.databinding.ActivityMainBinding
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator
import java.io.File

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    companion object { @Volatile private var syncing = false }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val ver = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "?" }
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT
        val root = binding.root as LinearLayout

        // Ряд иконок: убираем из него текстовые кнопки, добавляем ⬆ и 
        val iconRow = root.getChildAt(0) as LinearLayout
        iconRow.removeView(binding.btnSync)
        iconRow.removeView(binding.btnOrders)
        iconRow.setPadding(0, 0, 0, 0)
        val btnUpdate = Button(this).apply { text = "⬆" }
        btnUpdate.setOnClickListener { checkUpdate() }
        iconRow.addView(btnUpdate, LinearLayout.LayoutParams(wrap, wrap))
        val btnGantt = Button(this).apply { text = "📊" }
        btnGantt.setOnClickListener { startActivity(Intent(this, GanttActivity::class.java)) }
        iconRow.addView(btnGantt, LinearLayout.LayoutParams(wrap, wrap))
        for (b in listOf(binding.btnSettings, btnUpdate, btnGantt)) {
            b.minWidth = 0
            b.minimumWidth = 0
            b.setPadding(dp(10), 0, dp(10), 0)
            b.textSize = 16f
            b.maxLines = 1
        }
        root.removeView(iconRow)

        // Шапка: версия слева, иконки справа
        val tvVersion = TextView(this).apply {
            text = "Управление проектами v$ver"
            textSize = 12f
            maxLines = 1
            ellipsize = TextUtils.TruncateAt.END
        }
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(12), dp(6), dp(4), 0)
        }
        header.addView(tvVersion, LinearLayout.LayoutParams(0, wrap, 1f))
        header.addView(iconRow, LinearLayout.LayoutParams(wrap, wrap))
        root.addView(header, 0)

        // Отдельный ряд: Синхронизировать + Заказы (по половине ширины)
        binding.btnSync.maxLines = 1
        binding.btnSync.ellipsize = TextUtils.TruncateAt.END
        binding.btnOrders.maxLines = 1
        binding.btnOrders.ellipsize = TextUtils.TruncateAt.END
        val actions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(8), 0, dp(8), dp(4))
        }
        actions.addView(binding.btnSync, LinearLayout.LayoutParams(0, wrap, 1f))
        actions.addView(binding.btnOrders, LinearLayout.LayoutParams(0, wrap, 1f))
        root.addView(actions, 1)

        val tabs = listOf(
            "Сегодня" to "dashboard",
            "Финансы" to "finances",
            "Спецификация" to "specification",
            "Закупки" to "purchases",
            "Спец. закупок" to "purchase_spec",
            "Сроки" to "deadlines",
            "План-Факт" to "plan_fact",
            "Бюджет" to "budget",
            "История цен" to "price_history",
            "Переписка" to "correspondence"
        )
        binding.tabLayout.tabMode = TabLayout.MODE_SCROLLABLE
        binding.viewPager.adapter = object : androidx.viewpager2.adapter.FragmentStateAdapter(this) {
            override fun getItemCount() = tabs.size
            override fun createFragment(position: Int): Fragment = DataTabFragment.newInstance(tabs[position].second)
        }
        TabLayoutMediator(binding.tabLayout, binding.viewPager) { tab, position ->
            tab.text = tabs[position].first
        }.attach()

        binding.btnOrders.setOnClickListener { startActivity(Intent(this, OrdersActivity::class.java)) }
        binding.btnSettings.setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }
        binding.btnSync.setOnClickListener { startSync(false) }

        startSync(true)
    }

    override fun onResume() {
        super.onResume()
        val prefs = getSharedPreferences("app_settings", MODE_PRIVATE)
        if (prefs.getLong("last_sync", 0L) == 0L) startSync(true)
    }

    private fun startSync(auto: Boolean) {
        val prefs = getSharedPreferences("app_settings", MODE_PRIVATE)
        val login = prefs.getString("webdav_login", "") ?: ""
        val password = prefs.getString("webdav_password", "") ?: ""
        if (login.isEmpty() || password.isEmpty()) {
            if (!auto) Toast.makeText(this, "Сначала настройте облако Mail.ru в ⚙️", Toast.LENGTH_LONG).show()
            return
        }
        if (syncing) return
        syncing = true
        binding.btnSync.isEnabled = false
        binding.btnSync.text = "Синхронизация..."
        DatabaseSyncManager(this).syncDatabase { success, message ->
            runOnUiThread {
                syncing = false
                binding.btnSync.isEnabled = true
                binding.btnSync.text = "Синхронизировать"
                if (success) prefs.edit().putLong("last_sync", System.currentTimeMillis()).apply()
                Toast.makeText(this, message, if (auto && success) Toast.LENGTH_SHORT else Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun checkUpdate() {
        Toast.makeText(this, "Проверяю обновление в облаке...", Toast.LENGTH_SHORT).show()
        AppUpdateManager(this).check { result, message, file ->
            runOnUiThread {
                when (result) {
                    AppUpdateManager.Result.UPDATE ->
                        AlertDialog.Builder(this)
                            .setTitle("Обновление")
                            .setMessage(message)
                            .setPositiveButton("Установить") { _, _ -> installApk(file!!) }
                            .setNegativeButton("Позже", null)
                            .show()
                    else -> Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun installApk(file: File) {
        if (Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
            AlertDialog.Builder(this)
                .setTitle("Разрешите установку")
                .setMessage("Разрешите установку из этого приложения, затем снова нажмите ⬆.")
                .setPositiveButton("Открыть настройки") { _, _ ->
                    startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                }
                .setNegativeButton("Отмена", null).show()
            return
        }
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        startActivity(intent)
    }
}
