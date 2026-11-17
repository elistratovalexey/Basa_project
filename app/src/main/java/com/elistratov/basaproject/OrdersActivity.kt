package com.elistratov.basaproject

import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.elistratov.basaproject.databinding.ActivityOrdersBinding

class OrdersActivity : AppCompatActivity() {
    private lateinit var binding: ActivityOrdersBinding
    private lateinit var dbHelper: DatabaseHelper

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityOrdersBinding.inflate(layoutInflater)
        setContentView(binding.root)
        dbHelper = DatabaseHelper(this)

        loadFilters()
        binding.btnApplyFilters.setOnClickListener { applyFilters() }
        
        // Загрузка по умолчанию
        applyFilters()
    }

    private fun loadFilters() {
        val projects = dbHelper.getDistinctProjects()
        val manufacturers = dbHelper.getDistinctManufacturers()

        binding.spinnerProject.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, projects)
        binding.spinnerManufacturer.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, manufacturers)
    }

    private fun applyFilters() {
        val project = binding.spinnerProject.selectedItem?.toString()
        val manufacturer = binding.spinnerManufacturer.selectedItem?.toString()
        val isReceived = if (binding.cbReceived.isChecked) true else if (binding.cbNotReceived.isChecked) false else null

        val orders = dbHelper.getOrders(project, isReceived, manufacturer)
        
        val resultText = orders.joinToString("\n") { 
            "${if(it.isReceived) "✅" else "⬜"} ${it.project} | ${it.manufacturer} | ${it.name} | ${it.quantity} шт. | ${it.total} ₽" 
        }
        
        binding.tvOrdersResult.text = if (orders.isEmpty()) "Ничего не найдено" else "Найдено: ${orders.size}\n\n$resultText"
    }
}