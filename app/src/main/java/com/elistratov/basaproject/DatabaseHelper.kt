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

    data class TabRecord(val title: String, val details: String, val color: Long = 0L)

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

    private fun columnExists(table: String, col: String): Boolean = try {
        readableDatabase.rawQuery("PRAGMA table_info($table)", null).use { c ->
            var found = false
            while (c.moveToNext()) if (c.getString(1) == col) found = true
            found
        }
    } catch (e: Exception) { false }

    fun getProjectNames(): List<String> {
        val list = mutableListOf<String>()
        rows("SELECT name FROM projects ORDER BY name") { list.add(it.s("name")) }
        return list
    }

    private fun projectId(name: String): Int? {
        var id: Int? = null
        rows("SELECT id FROM projects WHERE name=?", arrayOf(name)) { c -> id = c.i("id") }
        return id
    }

    private fun mark(v: Int) = if (v == 1) "✓" else "—"
    private fun short(s: String, n: Int = 45) = if (s.length > n) s.take(n) + "…" else s

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

    fun tabData(tab: String, project: String?, search: String): List<TabRecord> {
        val out = when (tab) {
            "dashboard" -> dashboard(project)
            "finances" -> finances(project)
            "specification" -> specification(project)
            "purchases" -> purchases(project)
            "purchase_spec" -> purchaseSpec(project)
            "deadlines" -> deadlines(project)
            "plan_fact" -> planFact(project)
            "budget" -> budget(project)
            "price_history" -> priceHistory(project)
            else -> emptyList()
        }
        val q = search.trim().lowercase()
        return if (q.isEmpty()) out else out.filter { (it.title + "\n" + it.details).lowercase().contains(q) }
    }

    private fun dashboard(project: String?): List<TabRecord> {
        val today = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.time
        val overdue = mutableListOf<String>(); val soon = mutableListOf<String>()
        val noConfirm = mutableListOf<String>(); val priceReq = mutableListOf<String>()
        val where = if (project != null) "WHERE project_name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        val opt = listOf("status" to "st", "eta_date" to "eta").filter { columnExists("orders", it.first) }
            .joinToString("") { ", MAX(${it.first}) AS ${it.second}" }
        rows("SELECT order_batch_id AS bid, MAX(order_date) AS od, MAX(project_name) AS proj, MAX(supplier) AS sup, MAX(invoice_number) AS inv, MAX(payment_date) AS pd, MAX(max_delivery_date) AS maxd, MAX(received) AS rec, MAX(price_request) AS pr, MAX(price_request_num) AS prn$opt FROM orders $where GROUP BY order_batch_id", args) { c ->
            val st = c.s("st").trim()
            if (st == "Получен" || st == "Списан") return@rows
            val d0 = parseDate(c.s("od"))
            if (d0 != null && daysBetween(today, d0) > 180) return@rows
            val label = if (c.i("pr") == 1 && c.i("prn") > 0) "Z${c.i("prn")}" else c.s("bid")
            val head = "№$label · ${c.s("proj")} · ${c.s("sup")} · инвойс ${c.s("inv")}"
            val eta = parseDate(c.s("eta").ifEmpty { c.s("maxd") })
            if (c.i("rec") == 0 && eta != null) {
                val dd = daysBetween(eta, today)
                if (dd < 0) overdue.add("🔴 $head\nДата: ${fmtDate(eta)} · просрочено ${-dd} дн.")
                else if (dd <= 7) soon.add("🟡 $head\nДата: ${fmtDate(eta)} · через $dd дн.")
            }
            if (c.i("pr") == 1 && c.s("pd").isBlank()) priceReq.add("📩 $head\nДата заказа: ${c.s("od")}")
            if (d0 != null && c.i("rec") == 0 && st in listOf("", "Размещён", "Запрос цены", "КП получено")) {
                val age = daysBetween(today, d0)
                if (age in 6..45) noConfirm.add("📨 $head\nЗаказ от ${c.s("od")} · без подтверждения $age дн.")
            }
        }
        val unpaid = mutableListOf<String>(); val payWeek = mutableListOf<String>()
        val w2 = if (project != null) "WHERE pr.name=?" else ""
        rows("SELECT s.supplier, s.name, s.total, s.currency, s.payment_date, s.fully_paid, pr.name AS proj FROM purchase_specifications s LEFT JOIN projects pr ON pr.id=s.project_id $w2", args) { c ->
            if (c.i("fully_paid") == 0) {
                val pd = parseDate(c.s("payment_date"))
                if (pd != null && daysBetween(today, pd) > 180) return@rows
                val line = "🧾 ${c.s("proj")} · ${c.s("supplier")} · ${c.s("name")}\n${fmtMoney(c.d("total"))} ${c.s("currency")} · оплата: ${c.s("payment_date")}"
                unpaid.add(line)
                if (pd != null && daysBetween(pd, today) in 0..7) payWeek.add("💸 $line")
            }
        }
        val out = mutableListOf<TabRecord>()
        out.add(TabRecord("📊 Сводка",
            "🔴 Просроченные поставки: ${overdue.size}\n🟡 Поставка ≤ 7 дней: ${soon.size}\n💸 Оплаты на неделе: ${payWeek.size}\n🧾 Неоплаченные счета: ${unpaid.size}\n📨 Нет подтверждения 5–45 дн.: ${noConfirm.size}\n📩 Запросы цены без оплаты: ${priceReq.size}\n\nСкрыто: заказы «Получен»/«Списан» и старше 180 дней"))
        for (group in listOf(overdue, soon, payWeek, unpaid, noConfirm, priceReq))
            for (r in group) out.add(TabRecord(r.substringBefore('\n'), r))
        return out
    }

    private fun finances(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
        val totals = linkedMapOf<String, Double>()
        val header = StringBuilder()
        if (project != null) {
            rows("SELECT contract_date, contract_amount, contract_currency, delivery_address FROM projects WHERE name=?", arrayOf(project)) { c ->
                header.append("Договор: ${c.s("contract_date")} · ${c.s("contract_amount")} ${c.s("contract_currency")}\nАдрес доставки: ${c.s("delivery_address")}\n")
            }
        }
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT p.number, p.date, p.amount, p.currency, p.percent, p.paid, p.contract_date, pr.name AS proj FROM payments p LEFT JOIN projects pr ON pr.id=p.project_id $where ORDER BY pr.name, p.number", args) { c ->
            val cur = c.s("currency").ifEmpty { "—" }
            totals[cur] = (totals[cur] ?: 0.0) + parseNum(c.s("amount"))
            val paid = if (c.i("paid") == 1) "✓ оплачено" else "— не оплачено"
            out.add(TabRecord(
                "№${c.i("number")} · ${c.s("date")} · ${c.s("amount")} $cur · ${if (c.i("paid") == 1) "✓" else "—"}",
                "Проект: ${c.s("proj")}\nПлатёж №${c.i("number")}\nДата: ${c.s("date")}\nСумма: ${c.s("amount")} $cur\nПроцент: ${c.s("percent")}%\nСтатус: $paid\nКогда: ${c.s("contract_date")}",
                if (c.i("paid") == 1) 0xFFD9EAD3L else 0L
            ))
        }
        if (totals.isNotEmpty()) header.append("ИТОГО: ").append(totals.entries.joinToString(" | ") { "${fmtMoney(it.value)} ${it.key}" })
        if (header.isNotEmpty()) out.add(0, TabRecord("💰 Итоги / договор", header.toString()))
        return out
    }

    private fun specification(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
        val totals = linkedMapOf<String, Double>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT s.number, s.name, s.quantity, s.price, s.currency, pr.name AS proj FROM specifications s LEFT JOIN projects pr ON pr.id=s.project_id $where ORDER BY pr.name, s.number", args) { c ->
            val total = parseNum(c.s("quantity")) * parseNum(c.s("price"))
            val cur = c.s("currency").ifEmpty { "—" }
            totals[cur] = (totals[cur] ?: 0.0) + total
            out.add(TabRecord(
                "№${c.i("number")} · ${short(c.s("name"))} · ${fmtMoney(total)} $cur",
                "Проект: ${c.s("proj")}\nПозиция №${c.i("number")}\nНаименование: ${c.s("name")}\nКол-во: ${c.s("quantity")}\nЦена (с НДС 22%): ${c.s("price")} $cur\nСумма (с НДС 22%): ${fmtMoney(total)} $cur"
            ))
        }
        if (totals.isNotEmpty()) out.add(0, TabRecord("💰 Итоги спецификации",
            totals.entries.joinToString("\n") { "${fmtMoney(it.value)} ${it.key} · НДС 22%: ${fmtMoney(it.value * 0.22 / 1.22)}" }))
        return out
    }

    private fun purchases(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT p.number, p.manufacturer, p.subproject, p.kd, p.article, p.name, p.name_eng, p.quantity, p.ordered, p.order_date, p.in_order, p.received, p.receipt_date, p.price_request, p.note, pr.name AS proj FROM purchases p LEFT JOIN projects pr ON pr.id=p.project_id $where ORDER BY pr.name, p.number", args) { c ->
            val color = when {
                c.i("received") == 1 -> 0xFFD9EAD3L
                c.i("ordered") == 1 -> 0xFFFFF2CCL
                else -> 0L
            }
            out.add(TabRecord(
                "№${c.i("number")} · ${short(c.s("article"), 20)} · ${short(c.s("name"), 30)} · ${c.i("quantity")} шт",
                "Проект: ${c.s("proj")}\nЗакупка №${c.i("number")}\nАртикул: ${c.s("article")}\nНаименование (рус): ${c.s("name")}\nНаименование (анг): ${c.s("name_eng")}\nПроизводитель: ${c.s("manufacturer")}\nПодпроект: ${c.s("subproject")}\nКД: ${c.s("kd")}\nКол-во: ${c.i("quantity")}\nЗаказано: ${mark(c.i("ordered"))} ${c.s("order_date")}\nВ заказе: ${mark(c.i("in_order"))}\nПолучено: ${mark(c.i("received"))} ${c.s("receipt_date")}\nЗапрос цены: ${mark(c.i("price_request"))}\nПримечание: ${c.s("note")}",
                color
            ))
        }
        return out
    }

    private fun purchaseSpec(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT s.id, s.supplier, s.name, s.total, s.currency, s.payment_date, s.delivery_date, s.fully_paid, s.received, s.note, pr.name AS proj FROM purchase_specifications s LEFT JOIN projects