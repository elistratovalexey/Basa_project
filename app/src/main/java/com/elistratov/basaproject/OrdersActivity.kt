package com.elistratov.basaproject

import android.content.SharedPreferences
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
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
    private lateinit var spPayment: Spinner
    private lateinit var etDelivery: EditText
    private lateinit var cbPartial: CheckBox
    private lateinit var batchList: ListView
    private lateinit var batchAdapter: ArrayAdapter<String>
    private lateinit var tvHeader: TextView
    private lateinit var itemsBox: LinearLayout
    private lateinit var tvItemDetail: TextView
    private var allBatches: List<DatabaseHelper.OrderBatch> = emptyList()
    private var shownBatches: List<DatabaseHelper.OrderBatch> = emptyList()
    private var selectedItemView: TextView? = null

    private val syncListener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == "last_sync") runOnUiThread { reloadAfterSync() }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        db = DatabaseHelper(this)
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val match = LinearLayout.LayoutParams.MATCH_PARENT
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT

        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(8), dp(12), dp(8)) }

        val row1 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        spProject = Spinner(this); spManufacturer = Spinner(this); spReceived = Spinner(this)
        for (sp in listOf(spProject, spManufacturer, spReceived))
            row1.addView(sp, LinearLayout.LayoutParams(0, wrap, 1f))
        root.addView(row1, LinearLayout.LayoutParams(match, wrap))

        val row2 = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        etDelivery = EditText(this).apply { hint = "№ поставки"; setSingleLine() }
        spPayment = Spinner(this)
        cbPartial = CheckBox(this).apply { text = "Частично" }
        val btnReset = Button(this).apply { text = "✕" }
        row2.addView(etDelivery, LinearLayout.LayoutParams(0, wrap, 1f))
        row2.addView(spPayment, LinearLayout.LayoutParams(0, wrap, 1f))
        row2.addView(cbPartial, LinearLayout.LayoutParams(wrap, wrap))
        row2.addView(btnReset, LinearLayout.LayoutParams(wrap, wrap))
        root.addView(row2, LinearLayout.LayoutParams(match, wrap))

        batchList = ListView(this).apply { choiceMode = ListView.CHOICE_MODE_SINGLE }
        batchAdapter = object : ArrayAdapter<String>(this, android.R.layout.simple_list_item_activated_1, mutableListOf<String>()) {
            override fun getView(position: Int, convertView: View?, parent: ViewGroup): View {
                val v = super.getView(position, convertView, parent)
                v.setBackgroundColor(batchColor(shownBatches.getOrNull(position)))
                return v
            }
        }
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

        val listener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) = applyFilters()
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        spProject.onItemSelectedListener = listener
        spManufacturer.onItemSelectedListener = listener
        spReceived.onItemSelectedListener = listener
        spPayment.onItemSelectedListener = listener
        cbPartial.setOnCheckedChangeListener { _, _ -> applyFilters() }
        etDelivery.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) { applyFilters() }
        })
        btnReset.setOnClickListener {
            spProject.setSelection(0); spManufacturer.setSelection(0)
            spReceived.setSelection(0); spPayment.setSelection(0)
            cbPartial.isChecked = false
            etDelivery.setText("")
            applyFilters()
        }
        batchList.onItemClickListener = AdapterView.OnItemClickListener { _, _, position, _ ->
            batchList.setItemChecked(position, true)
            shownBatches.getOrNull(position)?.let { showBatch(it) }
        }

        if (!db.isDatabaseReady()) {
            setupSpinners(listOf("Все"), listOf("Все"))
            tvHeader.text = "База загружается... Если данные не появились, вернитесь на главный экран и дождитесь синхронизации."
            return
        }
        setupSpinners(db.getDistinctProjects(), db.getDistinctManufacturers())
        allBatches = db.getOrderBatches()
        applyFilters()
    }

    override fun onResume() {
        super.onResume()
        getSharedPreferences("app_settings", MODE_PRIVATE).registerOnSharedPreferenceChangeListener(syncListener)
    }

    override fun onPause() {
        getSharedPreferences("app_settings", MODE_PRIVATE).unregisterOnSharedPreferenceChangeListener(syncListener)
        super.onPause()
    }

    private fun reloadAfterSync() {
        if (!db.isDatabaseReady()) return
        setupSpinners(db.getDistinctProjects(), db.getDistinctManufacturers())
        allBatches = db.getOrderBatches()
        applyFilters()
    }

    private fun setupSpinners(projects: List<String>, manufacturers: List<String>) {
        fun ad(items: List<String>) = ArrayAdapter(this, android.R.layout.simple_spinner_item, items).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        spProject.adapter = ad(projects)
        spManufacturer.adapter = ad(manufacturers)
        spReceived.adapter = ad(listOf("Все", "Получено", "Не получено"))
        spPayment.adapter = ad(listOf("Все", "Есть дата", "Нет даты"))
    }

    private fun batchColor(b: DatabaseHelper.OrderBatch?): Int {
        if (b == null) return 0x00000000
        val st = b.status.trim()
        if (b.received || st == "Получен" || st == "Списан") return 0xFFD9EAD3.toInt()
        if (b.partialReceived) return 0xFFFFF2CC.toInt()
        if (db.batchOverdue(b)) return 0xFFF4CCCC.toInt()
        if (st in listOf("Подтверждён", "Оплачен", "Отгружен")) return 0xFFD0E0F0.toInt()
        return 0x00000000
    }

    private fun fmtQty(v: Double): String =
        if (v == v.toLong().toDouble()) v.toLong().toString() else v.toString()

    private fun applyFilters() {
        val proj = spProject.selectedItem?.toString()?.takeIf { it != "Все" }
        val man = spManufacturer.selectedItem?.toString()?.takeIf { it != "Все" }
        val recSel = spReceived.selectedItem?.toString()
        val paySel = spPayment.selectedItem?.toString()
        val dn = etDelivery.text.toString().trim()
        val partialOnly = cbPartial.isChecked
        shownBatches = allBatches.filter { b ->
            val projOk = proj == null || b.project == proj
            val manOk = man == null || b.manufacturer == man
            val recOk = when (recSel) {
                "Получено" -> b.received
                "Не получено" -> !b.received
                else -> true
            }
            val payOk = when (paySel) {
                "Есть дата" -> b.paymentDate.isNotBlank()
                "Нет даты" -> b.paymentDate.isBlank()
                else -> true
            }
            val dnOk = dn.isEmpty() || b.deliveryNumber.contains(dn, ignoreCase = true)
            val partOk = !partialOnly || b.partialReceived
            projOk && manOk && recOk && payOk && dnOk && partOk
        }
        batchAdapter.clear()
        batchAdapter.addAll(shownBatches.map { b ->
            val m = when { b.received -> "✅"; b.partialReceived -> "🟨"; else -> "⬜" }
            "$m №${b.label} · ${b.manufacturer} · ${b.project} · ${b.orderDate}" +
                (if (b.status.isNotEmpty()) " · ${b.status}" else "")
        })
        batchAdapter.notifyDataSetChanged()
        tvHeader.text = "Найдено заказов: ${shownBatches.size}. Выберите заказ в списке выше."
        itemsBox.removeAllViews()
        tvItemDetail.text = ""
        selectedItemView = null
    }

    private fun showBatch(b: DatabaseHelper.OrderBatch) {
        tvHeader.text = buildString {
            append("ЗАГОЛОВОК ЗАКАЗА №${b.label}\n")
            append("Дата заказа: ${b.orderDate}\nПроект: ${b.project}\nДата оплаты: ${b.paymentDate}\n")
            append("Номер инвойса: ${b.invoice}\nПоставщик: ${b.supplier}\nНомер поставки: ${b.deliveryNumber}\n")
            append("Производитель: ${b.manufacturer}\nПодпроект: ${b.subproject}\nКД: ${b.kd}\n")
            append("Доставка: ${b.deliveryDays} ${b.deliveryUnit}\nMin дата поставки: ${b.minDate}\nMax дата поставки: ${b.maxDate}\n")
            append("Получено: ${if (b.received) "✓" else "—"} ${b.receiptDate}\n")
            append("Частично получено: ${if (b.partialReceived) "✓" else "—"}\n")
            append("Дата списания: ${b.writeOffDate}\n")
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
            val q = item.quantity.toDouble()
            val r = item.qtyReceived
            val itemColor = when {
                q > 0 && r >= q -> 0xFFD9EAD3.toInt()
                r > 0 -> 0xFFFFF2CC.toInt()
                else -> 0x00000000
            }
            val baseText = "${item.id} · ${item.article} · ${item.name}\n" +
                "кол-во ${item.quantity} · получено ${fmtQty(r)} · остаток ${fmtQty(item.rest)} · ${item.price} ${item.currency}" +
                (if (item.itemStatus.isNotEmpty()) " · ${item.itemStatus}" else "")
            val tv = TextView(this).apply {
                text = baseText
                tag = baseText
                textSize = 14f
                setPadding(dp(6), dp(8), dp(6), dp(8))
                setBackgroundColor(itemColor)
                setOnClickListener { v ->
                    selectedItemView?.let { prev -> prev.text = prev.tag as String }
                    val tvv = v as TextView
                    tvv.text = "▶ " + (tvv.tag as String)
                    selectedItemView = tvv
                    tvItemDetail.text = buildString {
                        append("ПОЗИЦИЯ (ID ${item.id})\n")
                        append("Артикул: ${item.article}\nНаименование: ${item.name}\n")
                        if (item.nameEng.isNotEmpty()) append("Наименование (анг): ${item.nameEng}\n")
                        append("Статус артикула: ${item.itemStatus.ifEmpty { "—" }}\n")
                        append("Кол-во: ${item.quantity}\n")
                        append("Получено, кол-во: ${fmtQty(item.qtyReceived)}\n")
                        append("Остаток: ${fmtQty(item.rest)}\n")
                        append("Срок поставки: ${item.deliveryTerm} ${item.deliveryUnit}\n")
                        append("Цена: ${item.price} ${item.currency}\n")
                        val total = item.quantity * db.parseNum(item.price)
                        append("Сумма: ${"%.2f".format(total)} ${item.currency}\n")
                        append("Производитель: ${item.manufacturer}\nПодпроект: ${item.subproject}\nКД: ${item.kd}\n")
                        append("Получено: ${if (item.received) "✓" else "—"} ${item.receiptDate}\n")
                        append("Примечание: ${item.note}")
                    }
                }
            }
            itemsBox.addView(tv, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        }
        if (items.isEmpty()) tvItemDetail.text = "В этом заказе нет позиций"
    }
                   }
