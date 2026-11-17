package com.elistratov.basaproject

import android.os.Bundle
import android.widget.ArrayAdapter
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
        binding.btnApplyFilters.setOnClickListener { applyFilters() }

        if (!dbHelper.isDatabaseReady()) {
            binding.spinnerProject.adapter = simpleAdapter(listOf("Все"))
            binding.spinnerManufacturer.adapter = simpleAdapter(listOf("Все"))
            binding.tvOrdersResult.text =
                "База данных ещё не загружена.\n\n1. Вернитесь на главный экран\n2. Нажмите ⚙️ и настройте облако Mail.ru\n3. Нажмите «Синхронизировать»\n4. Снова откройте «Заказы»"
            return
        }
        loadFilters()
        applyFilters()
    }

    private fun simpleAdapter(items: List<String>) =
        ArrayAdapter(this, android.R.layout.simple_spinner_item, items).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }

    private fun loadFilters() {
        binding.spinnerProject.adapter = simpleAdapter(dbHelper.getDistinctProjects())
        binding.spinnerManufacturer.adapter = simpleAdapter(dbHelper.getDistinctManufacturers())
    }

    private fun applyFilters() {
        if (!dbHelper.isDatabaseReady()) {
            binding.tvOrdersResult.text = "База не загружена. Нажмите «Синхронизировать» на главном экране."
            return
        }
        val project = binding.spinnerProject.selectedItem?.toString()
        val manufacturer = binding.spinnerManufacturer.selectedItem?.toString()
        val isReceived = when {
            binding.cbReceived.isChecked -> true
            binding.cbNotReceived.isChecked -> false
            else -> null
        }
        val orders = dbHelper.getOrders(project, isReceived, manufacturer)
        if (orders.isEmpty()) {
            binding.tvOrdersResult.text = "Ничего не найдено"
            return
        }
        val sb = StringBuilder("Найдено позиций: ${orders.size}\n\n")
        for (o in orders) {
            sb.append(if (o.received) "✅" else "⬜")
            sb.append(" Заказ №${o.batchId} от ${o.orderDate}\n")
            sb.append("   ${o.project} | ${o.manufacturer} | ${o.supplier}\n")
            sb.append("   ${o.article} ${o.name}\n")
            sb.append("   ${o.quantity} шт × ${o.price} ${o.currency} = ${"%.2f".format(o.total)} ${o.currency}\n\n")
        }
        binding.tvOrdersResult.text = sb.toString()
    }
}