package com.elistratov.basaproject

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.viewpager2.widget.ViewPager2
import com.elistratov.basaproject.databinding.ActivityMainBinding
import com.google.android.material.tabs.TabLayoutMediator

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val tabs = arrayOf("Проекты", "Закупки", "Спецификации", "Финансы", "Сроки")
        binding.viewPager.adapter = object : androidx.viewpager2.adapter.FragmentStateAdapter(this) {
            override fun getItemCount() = tabs.size
            override fun createFragment(position: Int) = android.app.Fragment() // Заглушка, замените на реальные фрагменты
        }

        TabLayoutMediator(binding.tabLayout, binding.viewPager) { tab, position ->
            tab.text = tabs[position]
        }.attach()

        binding.btnOrders.setOnClickListener { startActivity(Intent(this, OrdersActivity::class.java)) }
        binding.btnSettings.setOnClickListener { startActivity(Intent(this, SettingsActivity::class.java)) }
        
        binding.btnSync.setOnClickListener {
            binding.btnSync.isEnabled = false
            binding.btnSync.text = "Синхронизация..."
            DatabaseSyncManager(this).syncDatabase { success, message ->
                runOnUiThread {
                    binding.btnSync.isEnabled = true
                    binding.btnSync.text = "Синхронизировать"
                    Toast.makeText(this, message, Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}