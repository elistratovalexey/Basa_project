package com.elistratov.basaproject

import android.content.Intent
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.elistratov.basaproject.databinding.ActivityMainBinding
import com.google.android.material.tabs.TabLayout
import com.google.android.material.tabs.TabLayoutMediator

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val ver = try { packageManager.getPackageInfo(packageName, 0).versionName } catch (e: Exception) { "?" }
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val tvVersion = TextView(this).apply {
            text = "Управление проектами v$ver"
            textSize = 12f
            setPadding(dp(12), dp(6), dp(12), 0)
        }
        (binding.root as LinearLayout).addView(tvVersion, 0)

        val tabs = listOf(
            "Сегодня" to "dashboard",
            "Финансы" to "finances",
            "Спецификация" to "specification",
            "Закупки" to "purchases",
            "Спец. закупок" to "purchase_spec",
            "Сроки" to "deadlines",
            "План-Факт" to "plan_fact",
            "Бюджет" to "budget"
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
        binding.btnSync.setOnClickListener {
            binding.btnSync.isEnabled = false
            binding.btnSync.text = "Синхронизация..."
            DatabaseSyncManager(this).syncDatabase { _, message ->
                runOnUiThread {
                    binding.btnSync.isEnabled = true
                    binding.btnSync.text = "Синхронизировать"
                    Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}