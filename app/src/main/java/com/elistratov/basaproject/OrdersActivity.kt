package com.elistratov.basaproject

import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class OrdersActivity : AppCompatActivity() {

    private lateinit var db: DatabaseHelper
    private lateinit var spProject: Spinner
    private lateinit var spManufacturer: Spinner
    private lateinit var spReceived: Spinner
    private lateinit var batchList: ListView
    private lateinit var batchAdapter: ArrayAdapter<String>
    private lateinit var tvHeader: TextView
    private lateinit var itemsBox: LinearLayout
    private lateinit var tvItemDetail: TextView
    private var allBatches: List<DatabaseHelper.OrderBatch> = emptyList()
    private var shownBatches: List<DatabaseHelper.OrderBatch> = emptyList()
    private var selectedItemView: View? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        db = DatabaseHelper(this)
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val match = LinearLayout.LayoutParams.MATCH_PARENT
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(8), dp(12), dp(8)) }

        val filterRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        spProject = Spinner(this); spManufacturer = Spinner(this); spReceived = Spinner(this)
        for (sp in listOf(spProject, spManufacturer, spReceived))
            filterRow.addView(sp, LinearLayout.LayoutParams(0, wrap, 1f))
        root.addView(filterRow, LinearLayout.LayoutParams(match, wrap))

        batchList = ListView(this).apply { choiceMode = ListView.CHOICE_MODE_SINGLE }
        batchAdapter = ArrayAdapter(this, android.R.layout.simple_list_item_activated_1, mutableListOf<String>())
        batchList.adapter = batchAdapter
        root.addView(batchList, LinearLayout.LayoutParams(match, 0, 1f))

        root.addView(View(this).apply { setBackgroundColor(0xFFCCCCCC.toInt()) }, LinearLayout.LayoutParams(match, dp(1)))

        tvHeader = TextView(this).apply { textSize = 14f; setTextIsSelectable(true); text = "Выберите заказ в списке выше" }
        itemsBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        tvItemDetail = TextView(this).apply { textSize = 14f; setTextIsSelectable(true); setPadding(0, dp(8), 0, dp(8)) }
        val bottomBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(tvHeader)
            addView(TextView(this@OrdersActivity).apply { text = "Позиции заказа (нажмите для подробностей):"; textSize = 14f; setPadding(0, dp(10), 0, dp(4)) })
            addView(itemsBox)
            addView(tvItemDetail)
        }
        val scroll = ScrollView(this).apply { addView(bottomBox, ViewGroup.LayoutParams(match, wrap)) }
        root.addView(scroll, LinearLayout.LayoutParams(match, 0, 1.3f))

        setContentView(root)

        if (!db.isDatabaseReady()) {
            tvHeader.text = "База не загружена. Вернитесь на главный экран, настройте облако (⚙️) и нажмите «Синхронизировать»."
            setupSpinners(listOf("Все"), listOf("Все"))
            return
        }
        setupSpinners(db.getDistinctProjects(), db.getDistinctManufacturers())
        allBatches = db.getOrderBatches()
        val listener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) = applyFilters()
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        spProject.onItemSelectedListener = listener
        spManufacturer.onItemSelectedListener = listener
        spReceived.onItemSelectedListener = listener

        batchList.onItemClickListener = AdapterView.OnItemClickListener { _, _, position, _ ->
            batchList.setItemChecked(position, true)
            shownBatches.getOrNull(position)?.let { showBatch(it) }
        }
        applyFilters()
    }

    private fun setupSpinners(projects: List<String>, manufacturers: List<String>) {
        fun ad(items: List<String>) = ArrayAdapter(this, android.R.layout.simple_spinner_item, items).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        spProject.adapter = ad(projects)
        spManufacturer.adapter = ad(manufacturers)
        spReceived.adapter = ad(listOf("Все", "Получено", "Не получено"))
    }

    private fun applyFilters() {
        val proj = spProject.selectedItem?.toString()?.takeIf { it != "Все" }
        val man = spManufacturer.selectedItem?.toString()?.takeIf { it != "Все" }
        val rec = when (spReceived.selectedItem?.toString()) { "Получено" -> true; "Не получено" -> false; else -> null }
        shownBatches = allBatches.filter { b ->
            (proj == null || b.project == proj) && (man == null || b.manufacturer == man) && (rec == null || b.received == rec)
        }
        batchAdapter.clear()
        batchAdapter.addAll(shownBatches.map { b ->
            "${if (b.received) "✅" else "⬜"} №${b.label} · ${b.manufacturer} · ${b.project} · ${b.orderDate}" +
                (if (b.status.isNotEmpty()) " · ${b.status}" else "")
        })
        batchAdapter.notifyDataSetChanged()
        tvHeader.text = "Найдено заказов: ${shownBatches.size}. Выберите заказ в списке выше."
        itemsBox.removeAllViews()
        tvItemDetail.text = ""
    }

    private fun showBatch(b: DatabaseHelper.OrderBatch) {
        tvHeader.text = buildString {
            append("ЗАГОЛОВОК ЗАКАЗА №${b.label}\n")
            append("Дата заказа: ${b.orderDate}\nПроект: ${b.project}\nДата оплаты: ${b.paymentDate}\n")
            append("Номер инвойса: ${b.invoice}\nПоставщик: ${b.supplier}\nНомер поставки: ${b.deliveryNumber}\n")
            append("Производитель: ${b.manufacturer}\nПодпроект: ${b.subproject}\nКД: ${b.kd}\n")
            append("Доставка: ${b.deliveryDays} ${b.deliveryUnit}\nMin дата поставки: ${b.minDate}\nMax дата поставки: ${b.maxDate}\n")
            append("Получено: ${if (b.received) "✓" else "—"} ${b.receiptDate}\nДата списания: ${b.writeOffDate}\n")
            append("Запрос цены: ${if (b.priceRequest) "✓ Z${b.priceRequestNum}" else "—"}\n")
            if (b.status.isNotEmpty()) append("Статус: ${b.status}\n")
            if (b.etaDate.isNotEmpty()) append("ETA: ${b.etaDate}\n")
            if (b.confirmDate.isNotEmpty()) append("Подтверждён: ${b.confirmDate}\n")
            if (b.shipDate.isNotEmpty()) append("Отгружен: ${b.shipDate}\n")
            if (b.tracking.isNotEmpty()) append("Трек: ${b.tracking}\n")
        }
        itemsBox.removeAllViews()
        tvItemDetail.text = ""
        selectedItemView = null
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val items = db.getOrderItems(b.batchId)
        for (item in items) {
            val tv = TextView(this).apply {
                text = "${item.id} · ${item.article} · ${item.name} · ${item.quantity} шт · ${item.price} ${item.currency}"
                textSize = 14f
                setPadding(dp(6), dp(8), dp(6), dp(8))
                setOnClickListener { v ->
                    selectedItemView?.setBackgroundColor(0x00000000)
                    v.setBackgroundColor(0x33FF9800)
                    selectedItemView = v
                    tvItemDetail.text = buildString {
                        append("ПОЗИЦИЯ (ID ${item.id})\n")
                        append("Артикул: ${item.article}\nНаименование: ${item.name}\n")
                        if (item.nameEng.isNotEmpty()) append("Наименование (анг): ${item.nameEng}\n")
                        append("Кол-во: ${item.quantity}\nСрок поставки: ${item.deliveryTerm} ${item.deliveryUnit}\n")
                        append("Цена: ${item.price} ${item.currency}\n")
                        val total = item.quantity * db.parseNum(item.price)
                        append("Сумма: ${"%.2f".format(total)} ${item.currency}\n")
                        append("Производитель: ${item.manufacturer}\nПодпроект: ${item.subproject}\nКД: ${item.kd}\n")
                        append("Получено: ${if (item.received) "✓" else "—"} ${item.receiptDate}")
                        if (item.qtyReceived > 0) append(" (принято: ${item.qtyReceived})")
                        append("\nПримечание: ${item.note}")
                    }
                }
            }
            itemsBox.addView(tv, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        if (items.isEmpty()) tvItemDetail.text = "В этом заказе нет позиций"
    }
}