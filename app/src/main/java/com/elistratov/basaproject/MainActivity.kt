package com.elistratov.basaproject

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
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
            override fun createFragment(position: Int): Fragment = TabFragment.newInstance(tabs[position])
        }
        TabLayoutMediator(binding.tabLayout, binding.viewPager) { tab, position ->
            tab.text = tabs[position]
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

// Именованный класс с пустым конструктором — обязателен для ViewPager2,
// анонимные фрагменты падают при пересоздании экрана
class TabFragment : Fragment() {
    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        val title = arguments?.getString("title") ?: ""
        return TextView(requireContext()).apply {
            text = "Раздел «$title»\n\nПросмотр данных этого раздела будет добавлен в следующей версии.\nСейчас доступен просмотр заказов — кнопка «Заказы»."
            textSize = 16f
            setPadding(48, 48, 48, 48)
        }
    }
    companion object {
        fun newInstance(title: String) = TabFragment().apply {
            arguments = Bundle().apply { putString("title", title) }
        }
    }
}