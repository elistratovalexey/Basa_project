package com.elistratov.basaproject

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class DatabaseHelper(private val context: Context) : SQLiteOpenHelper(context, "projects.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase?) {}
    override fun onUpgrade(db: SQLiteDatabase?, oldVersion: Int, newVersion: Int) {}

    // ================= служебные =================
    fun isDatabaseReady(): Boolean {
        val f = context.getDatabasePath("projects.db")
        if (!f.exists() || f.length() < 100) return false
        return try {
            readableDatabase.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'", null)
                .use { it.moveToFirst() }
        } catch (e: Exception) { false }
    }

    private fun Cursor.s(col: String): String { val i = getColumnIndex(col); return if (i >= 0 && !isNull(i)) getString(i) else "" }
    private fun Cursor.i(col: String): Int { val i = getColumnIndex(col); return if (i >= 0 && !isNull(i)) getInt(i) else 0 }
    private fun Cursor.d(col: String): Double { val i = getColumnIndex(col); return if (i >= 0 && !isNull(i)) getDouble(i) else 0.0 }

    private fun rows(sql: String, args: Array<String> = emptyArray(), block: (Cursor) -> Unit) {
        try { readableDatabase.rawQuery(sql, args).use { c -> while (c.moveToNext()) block(c) } } catch (e: Exception) { }
    }

    private fun tableExists(name: String): Boolean = try {
        readableDatabase.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name=?", arrayOf(name)).use { it.moveToFirst() }
    } catch (e: Exception) { false }

    fun getProjectNames(): List<String> {
        val list = mutableListOf<String>()
        rows("SELECT name FROM projects ORDER BY name") { list.add(it.s("name")) }
        return list
    }

    private fun mark(v: Int) = if (v == 1) "✓" else "—"

    fun parseNum(s: String?): Double {
        if (s.isNullOrBlank()) return 0.0
        val t = s.replace("\u00A0", "").replace(" ", "").replace("'", "")
        val cleaned = t.filter { it.isDigit() || it == ',' || it == '.' || it == '-' }
        if (cleaned.isEmpty()) return 0.0
        val lc = cleaned.lastIndexOf(','); val ld = cleaned.lastIndexOf('.')
        val norm = when {
            lc >= 0 && ld >= 0 -> if (lc > ld) cleaned.replace(".", "").replace(',', '.') else cleaned.replace(",", "")
            lc >= 0 -> cleaned.replace(',', '.')
            else -> cleaned
        }
        return norm.toDoubleOrNull() ?: 0.0
    }

    private fun fmtMoney(v: Double): String =
        DecimalFormat("#,##0.##", DecimalFormatSymbols(Locale("ru"))).format(v)

    private fun parseDate(s: String?): Date? {
        if (s.isNullOrBlank()) return null
        for (f in listOf("dd.MM.yyyy", "dd.MM.yy", "yyyy-MM-dd")) {
            try {
                val sdf = SimpleDateFormat(f, Locale.getDefault()); sdf.isLenient = false
                return sdf.parse(s.trim())
            } catch (e: Exception) { }
        }
        return null
    }

    private fun fmtDate(d: Date?): String =
        if (d == null) "" else SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(d)

    private fun daysBetween(a: Date, b: Date): Int = ((a.time - b.time) / 86400000L).toInt()

    private fun normCurrency(code: String?): String {
        val c = (code ?: "").trim().uppercase()
        return when {
            c.isEmpty() -> "RUB"
            c.contains("РУБ") || c.contains("₽") || c == "RUR" || c == "RUB" -> "RUB"
            c.contains("ДОЛЛАР") || c.contains("$") || c == "USD" -> "USD"
            c.contains("ЕВРО") || c.contains("€") || c == "EUR" -> "EUR"
            c.contains("ЮАН") || c.contains("¥") || c == "CNY" -> "CNY"
            c.contains("ЛИР") || c.contains("₺") || c == "TRY" -> "TRY"
            else -> c
        }
    }

    private fun getRate(code: String?, dateStr: String? = null): Double {
        val c = normCurrency(code)
        if (c == "RUB" || !tableExists("currency_rates")) return 1.0
        try {
            val iso = parseDate(dateStr)?.let { SimpleDateFormat("yyyy-MM-dd", Locale.US).format(it) }
            if (iso != null) {
                readableDatabase.rawQuery("SELECT rate FROM currency_rates WHERE code=? AND date<=? ORDER BY date DESC LIMIT 1", arrayOf(c, iso))
                    .use { if (it.moveToFirst()) return it.getDouble(0) }
            }
            readableDatabase.rawQuery("SELECT rate FROM currency_rates WHERE code=? ORDER BY date DESC LIMIT 1", arrayOf(c))
                .use { if (it.moveToFirst()) return it.getDouble(0) }
        } catch (e: Exception) { }
        return 1.0
    }

    private fun isWorkingDay(cal: Calendar): Boolean {
        val dow = cal.get(Calendar.DAY_OF_WEEK)
        if (dow == Calendar.SATURDAY || dow == Calendar.SUNDAY) return false
        val md = (cal.get(Calendar.MONTH) + 1) * 100 + cal.get(Calendar.DAY_OF_MONTH)
        return md !in setOf(101, 102, 103, 104, 105, 106, 107, 108, 223, 308, 501, 509, 612, 1104)
    }

    private fun calcDeadline(baseStr: String?, termStr: String?, unit: String?): String {
        val base = parseDate(baseStr) ?: return ""
        val term = termStr?.trim()?.toIntOrNull() ?: return ""
        if (term <= 0) return ""
        val cal = Calendar.getInstance(); cal.time = base
        when (unit) {
            "Календарные дни" -> cal.add(Calendar.DAY_OF_MONTH, term)
            "Недели" -> cal.add(Calendar.WEEK_OF_YEAR, term)
            "Месяцы" -> cal.add(Calendar.MONTH, term)
            "Рабочие дни" -> { var added = 0; while (added < term) { cal.add(Calendar.DAY_OF_MONTH, 1); if (isWorkingDay(cal)) added++ } }
            else -> return ""
        }
        return fmtDate(cal.time)
    }

    // ================= входная точка для вкладок =================
    fun tabData(tab: String, project: String?, search: String): List<String> {
        val out = when (tab) {
            "dashboard" -> dashboard(project)
            "finances" -> finances(project)
            "specification" -> specification(project)
            "purchases" -> purchases(project)
            "purchase_spec" -> purchaseSpec(project)
            "deadlines" -> deadlines(project)
            "plan_fact" -> planFact(project)
            "budget" -> budget(project)
            else -> emptyList()
        }
        val q = search.trim().lowercase()
        return if (q.isEmpty()) out else out.filter { it.lowercase().contains(q) }
    }

    // ================= Сегодня =================
    private fun dashboard(project: String?): List<String> {
        val out = mutableListOf<String>()
        val today = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.time
        val overdue = mutableListOf<String>(); val soon = mutableListOf<String>()
        val noConfirm = mutableListOf<String>(); val priceReq = mutableListOf<String>()
        val where = if (project != null) "WHERE project_name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        val base = "SELECT order_batch_id AS bid, MAX(order_date) AS od, MAX(project_name) AS proj, MAX(supplier) AS sup, MAX(invoice_number) AS inv, MAX(payment_date) AS pd, MAX(max_delivery_date) AS maxd, MAX(received) AS rec, MAX(price_request) AS pr, MAX(price_request_num) AS prn"
        val block: (Cursor) -> Unit = { c ->
            val label = if (c.i("pr") == 1 && c.i("prn") > 0) "Z${c.i("prn")}" else c.s("bid")
            val head = "№$label · ${c.s("proj")} · ${c.s("sup")} · инвойс ${c.s("inv")}"
            val eta = parseDate(c.s("eta").ifEmpty { c.s("maxd") })
            if (c.i("rec") == 0 && eta != null) {
                val dd = daysBetween(eta, today)
                if (dd < 0) overdue.add("🔴 $head\nДата: ${fmtDate(eta)} · просрочено ${-dd} дн.")
                else if (dd <= 7) soon.add("🟡 $head\nДата: ${fmtDate(eta)} · через $dd дн.")
            }
            if (c.i("pr") == 1 && c.s("pd").isBlank()) priceReq.add("📩 $head\nДата заказа: ${c.s("od")}")
            val d0 = parseDate(c.s("od"))
            if (d0 != null && c.i("rec") == 0 && c.s("st") in listOf("", "Размещён", "Запрос цены", "КП получено")) {
                val age = daysBetween(today, d0)
                if (age > 5) noConfirm.add("📨 $head\nЗаказ от ${c.s("od")} · без подтверждения $age дн.")
            }
        }
        try {
            readableDatabase.rawQuery("$base, MAX(status) AS st, MAX(eta_date) AS eta FROM orders $where GROUP BY order_batch_id", args)
                .use { c -> while (c.moveToNext()) block(c) }
        } catch (e: Exception) { rows("$base FROM orders $where GROUP BY order_batch_id", args, block) }

        val unpaid = mutableListOf<String>(); val payWeek = mutableListOf<String>()
        val w2 = if (project != null) "WHERE pr.name=?" else ""
        rows("SELECT s.supplier, s.name, s.total, s.currency, s.payment_date, s.fully_paid, pr.name AS proj FROM purchase_specifications s LEFT JOIN projects pr ON pr.id=s.project_id $w2", args) { c ->
            if (c.i("fully_paid") == 0) {
                val line = "🧾 ${c.s("proj")} · ${c.s("supplier")} · ${c.s("name")}\n${fmtMoney(c.d("total"))} ${c.s("currency")} · оплата: ${c.s("payment_date")}"
                unpaid.add(line)
                val pd = parseDate(c.s("payment_date"))
                if (pd != null && daysBetween(pd, today) in 0..7) payWeek.add("💸 $line")
            }
        }
        out.add("🔴 Просроченные поставки: ${overdue.size}"); out.addAll(overdue)
        out.add("🟡 Поставка ≤ 7 дней: ${soon.size}"); out.addAll(soon)
        out.add("💸 Оплаты на неделе: ${payWeek.size}"); out.addAll(payWeek)
        out.add("🧾 Неоплаченные счета: ${unpaid.size}"); out.addAll(unpaid)
        out.add("📨 Нет подтверждения > 5 дн.: ${noConfirm.size}"); out.addAll(noConfirm)
        out.add("📩 Запросы цены без оплаты: ${priceReq.size}"); out.addAll(priceReq)
        return out
    }

    // ================= Финансы =================
    private fun finances(project: String?): List<String> {
        val out = mutableListOf<String>()
        val totals = linkedMapOf<String, Double>()
        if (project != null) {
            rows("SELECT contract_date, contract_amount, contract_currency, delivery_address FROM projects WHERE name=?", arrayOf(project)) { c ->
                out.add("Договор: ${c.s("contract_date")} · ${c.s("contract_amount")} ${c.s("contract_currency")}\nАдрес доставки: ${c.s("delivery_address")}")
            }
        }
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT p.number, p.date, p.amount, p.currency, p.percent, p.paid, p.contract_date, pr.name AS proj FROM payments p LEFT JOIN projects pr ON pr.id=p.project_id $where ORDER BY pr.name, p.number", args) { c ->
            val cur = c.s("currency").ifEmpty { "—" }
            totals[cur] = (totals[cur] ?: 0.0) + parseNum(c.s("amount"))
            out.add("№${c.i("number")} · ${c.s("proj")}\n${c.s("date")} · ${c.s("amount")} $cur · ${c.s("percent")}%\n${if (c.i("paid") == 1) "✓ оплачено" else "— не оплачено"} · когда: ${c.s("contract_date")}")
        }
        if (totals.isNotEmpty()) out.add("ИТОГО: " + totals.entries.joinToString(" | ") { "${fmtMoney(it.value)} ${it.key}" })
        return out
    }

    // ================= Спецификация =================
    private fun specification(project: String?): List<String> {
        val out = mutableListOf<String>()
        val totals = linkedMapOf<String, Double>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT s.number, s.name, s.quantity, s.price, s.currency, pr.name AS proj FROM specifications s LEFT JOIN projects pr ON pr.id=s.project_id $where ORDER BY pr.name, s.number", args) { c ->
            val qty = parseNum(c.s("quantity")); val price = parseNum(c.s("price"))
            val total = qty * price
            val cur = c.s("currency").ifEmpty { "—" }
            totals[cur] = (totals[cur] ?: 0.0) + total
            out.add("№${c.i("number")} · ${c.s("proj")}\n${c.s("name")}\n${c.s("quantity")} × ${c.s("price")} $cur = ${fmtMoney(total)} $cur (с НДС 22%)")
        }
        if (totals.isNotEmpty()) out.add("ИТОГО: " + totals.entries.joinToString(" | ") {
            "${fmtMoney(it.value)} ${it.key} (НДС 22%: ${fmtMoney(it.value * 0.22 / 1.22)})"
        })
        return out
    }

    // ================= Закупки =================
    private fun purchases(project: String?): List<String> {
        val out = mutableListOf<String>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT p.number, p.manufacturer, p.subproject, p.kd, p.article, p.name, p.name_eng, p.quantity, p.ordered, p.order_date, p.in_order, p.received, p.price_request, p.note, pr.name AS proj FROM purchases p LEFT JOIN projects pr ON pr.id=p.project_id $where ORDER BY pr.name, p.number", args) { c ->
            out.add(("№${c.i("number")} · ${c.s("proj")}\n" +
                "${c.s("article")} — ${c.s("name")}\n" +
                "${c.s("manufacturer")} · подпроект: ${c.s("subproject")} · КД: ${c.s("kd")} · ${c.i("quantity")} шт\n" +
                "Заказано ${mark(c.i("ordered"))} ${c.s("order_date")} · В заказе ${mark(c.i("in_order"))} · Получено ${mark(c.i("received"))} · Запрос цены ${mark(c.i("price_request"))}\n" +
                c.s("note")).trim())
        }
        return out
    }

    // ================= Спецификация Закупок =================
    private fun purchaseSpec(project: String?): List<String> {
        val out = mutableListOf<String>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT s.id, s.supplier, s.name, s.total, s.currency, s.payment_date, s.delivery_date, s.fully_paid, s.received, s.note, pr.name AS proj FROM purchase_specifications s LEFT JOIN projects pr ON pr.id=s.project_id $where ORDER BY s.id DESC", args) { c ->
            val id = c.i("id")
            val sb = StringBuilder()
            sb.append("Счёт №$id · ${c.s("proj")}\n${c.s("supplier")} · ${c.s("name")}\n")
            sb.append("${fmtMoney(c.d("total"))} ${c.s("currency")} · оплата: ${c.s("payment_date")} · поставка: ${c.s("delivery_date")}\n")
            sb.append(if (c.i("fully_paid") == 1) "✓ оплачен полностью" else "— не оплачен полностью")
            sb.append(if (c.i("received") == 1) " · ✓ получен" else " · — не получен")
            rows("SELECT name, quantity, price, total, delivery_term, delivery_unit FROM purchase_spec_items WHERE spec_id=? ORDER BY id", arrayOf(id.toString())) { it2 ->
                sb.append("\n  • ${it2.s("name")} · ${fmtMoney(it2.d("quantity"))} × ${fmtMoney(it2.d("price"))} = ${fmtMoney(it2.d("total"))} · срок ${it2.s("delivery_term")} ${it2.s("delivery_unit")}")
            }
            rows("SELECT number, date, amount, currency, percent, paid FROM purchase_payments WHERE spec_id=? ORDER BY number", arrayOf(id.toString())) { p ->
                sb.append("\n  💰 №${p.i("number")} · ${p.s("date")} · ${fmtMoney(p.d("amount"))} ${p.s("currency")} · ${p.s("percent")}% · ${mark(p.i("paid"))}")
            }
            if (c.s("note").isNotEmpty()) sb.append("\n${c.s("note")}")
            out.add(sb.toString())
        }
        return out
    }

    // ================= Сроки =================
    private fun firstPaymentDate(project: String): String {
        var best: Date? = null
        rows("SELECT p.date FROM payments p JOIN projects pr ON pr.id=p.project_id WHERE pr.name=?", arrayOf(project)) { c ->
            val d = parseDate(c.s("date"))
            if (d != null) { val b = best; if (b == null || d.before(b)) best = d }
        }
        return fmtDate(best)
    }

    private fun deadlines(project: String?): List<String> {
        val out = mutableListOf<String>()
        val where = if (project != null) "WHERE name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT name, contract_date, contract_amount, contract_currency, del_term, del_unit, del_base_date, confirmation_date, work_start, work_term, work_unit, delivery_address FROM projects $where ORDER BY name", args) { c ->
            val name = c.s("name")
            val baseType = c.s("del_base_date").ifEmpty { "От даты договора" }
            val baseDate = when (baseType) {
                "От даты подтверждения" -> c.s("confirmation_date")
                "От даты первого платежа" -> firstPaymentDate(name)
                else -> c.s("contract_date")
            }
            val delivery = calcDeadline(baseDate, c.s("del_term"), c.s("del_unit").ifEmpty { "Календарные дни" })
            val work = calcDeadline(c.s("work_start"), c.s("work_term"), c.s("work_unit").ifEmpty { "Календарные дни" })
            out.add("Проект: $name\nДоговор: ${c.s("contract_date")} · ${c.s("contract_amount")} ${c.s("contract_currency")}\n" +
                "Поставка: ${c.s("del_term")} ${c.s("del_unit")} ($baseType: ${baseDate.ifEmpty { "нет даты" }}) → ${delivery.ifEmpty { "—" }}\n" +
                "Работы: ${c.s("work_start")} + ${c.s("work_term")} ${c.s("work_unit")} → ${work.ifEmpty { "—" }}\n" +
                "Подтверждение: ${c.s("confirmation_date").ifEmpty { "—" }}\nАдрес: ${c.s("delivery_address")}")
        }
        return out
    }

    // ================= План-Факт =================
    private fun planFact(project: String?): List<String> {
        if (!tableExists("plan_fact")) return listOf("Таблица «План-Факт» отсутствует в базе")
        val out = mutableListOf<String>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT f.number, f.name, f.work_type, f.status, f.note, pr.name AS proj FROM plan_fact f LEFT JOIN projects pr ON pr.id=f.project_id $where ORDER BY pr.name, f.number", args) { c ->
            out.add(("№${c.i("number")} · ${c.s("proj")}\n${c.s("name")}\nТип: ${c.s("work_type")} · Статус: ${c.s("status")}\n" + c.s("note")).trim())
        }
        return out
    }

    // ================= Бюджет =================
    private fun budget(project: String?): List<String> {
        val out = mutableListOf<String>()
        if (!tableExists("currency_rates")) out.add("⚠️ Курсы валют не найдены в базе — пересчёт в рубли по курсу 1")
        val projects = if (project != null) listOf(project) else getProjectNames()
        for (name in projects) {
            var planSell = 0.0; var income = 0.0; var planBuy = 0.0; var received = 0.0; var paidSup = 0.0
            rows("SELECT s.quantity, s.price, s.currency FROM specifications s JOIN projects pr ON pr.id=s.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                planSell += parseNum(c.s("quantity")) * parseNum(c.s("price")) * getRate(c.s("currency"))
            }
            rows("SELECT p.amount, p.currency, p.paid FROM payments p JOIN projects pr ON pr.id=p.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                if (c.i("paid") == 1) income += parseNum(c.s("amount")) * getRate(c.s("currency"))
            }
            rows("SELECT quantity, price, currency, received FROM orders WHERE project_name=?", arrayOf(name)) { c ->
                val v = c.i("quantity") * parseNum(c.s("price")) * getRate(c.s("currency"))
                planBuy += v
                if (c.i("received") == 1) received += v
            }
            rows("SELECT pp.amount, pp.currency, pp.paid FROM purchase_payments pp JOIN purchase_specifications s ON s.id=pp.spec_id JOIN projects pr ON pr.id=s.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                if (c.i("paid") == 1) paidSup += parseNum(c.s("amount")) * getRate(c.s("currency"))
            }
            out.add("Проект: $name\nПлан продажи: ${fmtMoney(planSell)} ₽\nОплачено заказчиком: ${fmtMoney(income)} ₽\n" +
                "План закупки: ${fmtMoney(planBuy)} ₽\nПолучено товара: ${fmtMoney(received)} ₽\nОплачено поставщикам: ${fmtMoney(paidSup)} ₽\n" +
                "Маржа (факт): ${fmtMoney(income - paidSup)} ₽\nМаржа (план): ${fmtMoney(planSell - planBuy)} ₽")
        }
        return out
    }

    // ================= Заказы (экран «Заказы») =================
    fun getDistinctProjects(): List<String> = distinctValues("project_name")
    fun getDistinctManufacturers(): List<String> = distinctValues("manufacturer")

    private fun distinctValues(column: String): List<String> {
        val list = mutableListOf("Все")
        if (!isDatabaseReady()) return list
        rows("SELECT DISTINCT $column FROM orders WHERE $column IS NOT NULL AND $column != '' ORDER BY $column") { list.add(it.s(column)) }
        return list
    }

    fun getOrders(project: String?, isReceived: Boolean?, manufacturer: String?): List<Order> {
        val orders = mutableListOf<Order>()
        if (!isDatabaseReady()) return orders
        val query = StringBuilder("SELECT id, order_batch_id, project_name, manufacturer, article, name, quantity, price, currency, received, supplier, order_date FROM orders WHERE 1=1")
        val args = mutableListOf<String>()
        if (!project.isNullOrEmpty() && project != "Все") { query.append(" AND project_name = ?"); args.add(project) }
        if (isReceived != null) { query.append(" AND received = ?"); args.add(if (isReceived) "1" else "0") }
        if (!manufacturer.isNullOrEmpty() && manufacturer != "Все") { query.append(" AND manufacturer LIKE ?"); args.add("%$manufacturer%") }
        query.append(" ORDER BY order_batch_id DESC, id")
        rows(query.toString(), args.toTypedArray()) { c ->
            orders.add(Order(
                id = c.i("id"), batchId = c.i("order_batch_id"),
                project = c.s("project_name"), manufacturer = c.s("manufacturer"),
                article = c.s("article"), name = c.s("name"),
                quantity = c.i("quantity"),
                price = parseNum(c.s("price")),
                currency = c.s("currency"), received = c.i("received") == 1,
                supplier = c.s("supplier"), orderDate = c.s("order_date")
            ))
        }
        return orders
    }

    data class Order(
        val id: Int, val batchId: Int, val project: String, val manufacturer: String,
        val article: String, val name: String, val quantity: Int, val price: Double,
        val currency: String, val received: Boolean, val supplier: String, val orderDate: String
    ) {
        val total: Double get() = quantity * price
    }
}