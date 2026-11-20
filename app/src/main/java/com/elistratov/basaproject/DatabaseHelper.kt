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
        rows("SELECT s.id, s.supplier, s.name, s.total, s.currency, s.payment_date, s.delivery_date, s.fully_paid, s.received, s.note, pr.name AS proj FROM purchase_specifications s LEFT JOIN projects pr ON pr.id=s.project_id $where ORDER BY s.id DESC", args) { c ->
            val id = c.i("id")
            val sb = StringBuilder()
            sb.append("Проект: ${c.s("proj")}\nПоставщик: ${c.s("supplier")}\nСпецификация: ${c.s("name")}\n")
            sb.append("Сумма: ${fmtMoney(c.d("total"))} ${c.s("currency")}\nДата оплаты: ${c.s("payment_date")}\nДата поставки: ${c.s("delivery_date")}\n")
            sb.append(if (c.i("fully_paid") == 1) "✓ оплачен полностью" else "— не оплачен полностью")
            sb.append(if (c.i("received") == 1) " · ✓ получен" else " · — не получен")
            rows("SELECT name, quantity, price, total, delivery_term, delivery_unit FROM purchase_spec_items WHERE spec_id=? ORDER BY id", arrayOf(id.toString())) { it2 ->
                sb.append("\n  • ${it2.s("name")} · ${fmtMoney(it2.d("quantity"))} × ${fmtMoney(it2.d("price"))} = ${fmtMoney(it2.d("total"))} · срок ${it2.s("delivery_term")} ${it2.s("delivery_unit")}")
            }
            rows("SELECT number, date, amount, currency, percent, paid FROM purchase_payments WHERE spec_id=? ORDER BY number", arrayOf(id.toString())) { p ->
                sb.append("\n  💰 платёж №${p.i("number")} · ${p.s("date")} · ${fmtMoney(p.d("amount"))} ${p.s("currency")} · ${p.s("percent")}% · ${mark(p.i("paid"))}")
            }
            if (c.s("note").isNotEmpty()) sb.append("\nПримечание: ${c.s("note")}")
            out.add(TabRecord(
                "Счёт №$id · ${short(c.s("supplier"), 20)} · ${fmtMoney(c.d("total"))} ${c.s("currency")} · ${if (c.i("fully_paid") == 1) "✓" else "—"}",
                sb.toString(),
                if (c.i("fully_paid") == 1) 0xFFD9EAD3L else 0L
            ))
        }
        return out
    }

    private fun firstPaymentDate(project: String): String {
        var best: Date? = null
        rows("SELECT p.date FROM payments p JOIN projects pr ON pr.id=p.project_id WHERE pr.name=?", arrayOf(project)) { c ->
            val d = parseDate(c.s("date"))
            if (d != null) { val b = best; if (b == null || d.before(b)) best = d }
        }
        return fmtDate(best)
    }

    private fun deadlines(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
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
            out.add(TabRecord(
                "$name · поставка → ${delivery.ifEmpty { "—" }}",
                "Проект: $name\nДоговор: ${c.s("contract_date")} · ${c.s("contract_amount")} ${c.s("contract_currency")}\n" +
                    "Поставка: ${c.s("del_term")} ${c.s("del_unit")}\nСчитать от: $baseType (${baseDate.ifEmpty { "нет даты" }})\nДата поставки: ${delivery.ifEmpty { "—" }}\n" +
                    "Работы: начало ${c.s("work_start")} + ${c.s("work_term")} ${c.s("work_unit")} → ${work.ifEmpty { "—" }}\n" +
                    "Дата подтверждения: ${c.s("confirmation_date").ifEmpty { "—" }}\nАдрес доставки: ${c.s("delivery_address")}"
            ))
        }
        return out
    }

    private fun planFact(project: String?): List<TabRecord> {
        if (!tableExists("plan_fact")) return listOf(TabRecord("Нет данных", "Таблица «План-Факт» отсутствует в базе"))
        val out = mutableListOf<TabRecord>()
        val where = if (project != null) "WHERE pr.name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        rows("SELECT f.number, f.name, f.work_type, f.status, f.note, pr.name AS proj FROM plan_fact f LEFT JOIN projects pr ON pr.id=f.project_id $where ORDER BY pr.name, f.number", args) { c ->
            out.add(TabRecord(
                "№${c.i("number")} · ${short(c.s("name"), 35)} · ${c.s("status")}",
                "Проект: ${c.s("proj")}\nРабота №${c.i("number")}\nНаименование: ${c.s("name")}\nТип работ: ${c.s("work_type")}\nСтатус: ${c.s("status")}\nПримечание: ${c.s("note")}",
                if (c.s("status") == "Выполнено") 0xFFD9EAD3L else 0L
            ))
        }
        return out
    }

    private fun getOrdersCostCoef(project: String): Double {
        if (!columnExists("projects", "orders_cost_coef")) return 1.8
        var coef = 1.8
        rows("SELECT orders_cost_coef FROM projects WHERE name=?", arrayOf(project)) { c ->
            val v = c.d("orders_cost_coef")
            if (v > 0) coef = v
        }
        return coef
    }

    private fun budget(project: String?): List<TabRecord> {
        val out = mutableListOf<TabRecord>()
        if (!tableExists("currency_rates")) out.add(TabRecord("⚠️ Курсы валют", "Курсы не найдены в базе — пересчёт в рубли по курсу 1"))
        val projects = if (project != null) listOf(project) else getProjectNames()
        for (name in projects) {
            val coef = getOrdersCostCoef(name)
            var planSell = 0.0; var income = 0.0
            var planBuyOrders = 0.0; var ordersBase = 0.0; var planBuySpecs = 0.0
            var received = 0.0; var paidSup = 0.0
            rows("SELECT s.quantity, s.price, s.currency FROM specifications s JOIN projects pr ON pr.id=s.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                planSell += parseNum(c.s("quantity")) * parseNum(c.s("price")) * getRate(c.s("currency"))
            }
            rows("SELECT p.amount, p.currency, p.paid FROM payments p JOIN projects pr ON pr.id=p.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                if (c.i("paid") == 1) income += parseNum(c.s("amount")) * getRate(c.s("currency"))
            }
            rows("SELECT quantity, price, currency, received FROM orders WHERE project_name=?", arrayOf(name)) { c ->
                val base = c.i("quantity") * parseNum(c.s("price"))
                val rate = getRate(c.s("currency"))
                ordersBase += base * rate
                val v = base * coef * rate
                planBuyOrders += v
                if (c.i("received") == 1) received += v
            }
            rows("SELECT s.id, s.total, s.quantity, s.price, s.currency, s.received FROM purchase_specifications s JOIN projects pr ON pr.id=s.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                val specId = c.i("id")
                val rate = getRate(c.s("currency"))
                val isRec = c.i("received") == 1
                var base = c.d("total")
                if (base <= 0) base = c.d("quantity") * c.d("price")
                if (base > 0) {
                    val rv = base * rate
                    planBuySpecs += rv
                    if (isRec) received += rv
                } else {
                    rows("SELECT total, quantity, price FROM purchase_spec_items WHERE spec_id=?", arrayOf(specId.toString())) { it2 ->
                        var iv = it2.d("total")
                        if (iv <= 0) iv = it2.d("quantity") * it2.d("price")
                        if (iv > 0) {
                            val rv = iv * rate
                            planBuySpecs += rv
                            if (isRec) received += rv
                        }
                    }
                }
            }
            rows("SELECT pp.amount, pp.currency, pp.paid FROM purchase_payments pp JOIN purchase_specifications s ON s.id=pp.spec_id JOIN projects pr ON pr.id=s.project_id WHERE pr.name=?", arrayOf(name)) { c ->
                if (c.i("paid") == 1) paidSup += parseNum(c.s("amount")) * getRate(c.s("currency"))
            }
            val planBuy = planBuyOrders + planBuySpecs
            val balance = income - paidSup
            val markup = planBuyOrders - ordersBase
            out.add(TabRecord(
                "$name · баланс: ${fmtMoney(balance)} ₽",
                "Проект: $name\nКоэффициент заказов: ×${fmtMoney(coef)}\n\n" +
                    "План продажи: ${fmtMoney(planSell)} ₽\n" +
                    "Оплачено клиентом: ${fmtMoney(income)} ₽\n\n" +
                    "Закупки (план, всего): ${fmtMoney(planBuy)} ₽\n" +
                    "  в т.ч. заказы (×${fmtMoney(coef)}): ${fmtMoney(planBuyOrders)} ₽\n" +
                    "  в т.ч. счета поставщиков: ${fmtMoney(planBuySpecs)} ₽\n" +
                    "  наценка на заказы: ${fmtMoney(markup)} ₽\n\n" +
                    "Оплачено поставщикам: ${fmtMoney(paidSup)} ₽\n" +
                    "Баланс (клиент − поставщики): ${fmtMoney(balance)} ₽\n\n" +
                    "Получено (закупки): ${fmtMoney(received)} ₽\n" +
                    "Маржа план: ${fmtMoney(planSell - planBuy)} ₽\n" +
                    "Маржа факт: ${fmtMoney(balance)} ₽",
                if (balance >= 0) 0xFFD9EAD3L else 0xFFF4CCCCL
            ))
        }
        return out
    }

    private data class PriceRow(val article: String, val name: String, val manufacturer: String,
                                val supplier: String, val price: Double, val currency: String,
                                val date: String, val proj: String, val source: String)

    private fun priceHistory(project: String?): List<TabRecord> {
        val list = mutableListOf<PriceRow>()
        val where = if (project != null) "WHERE project_name=?" else ""
        val args = if (project != null) arrayOf(project) else emptyArray()
        if (tableExists("price_history")) {
            rows("SELECT article, name, manufacturer, supplier, price, currency, date, project_name, source FROM price_history $where", args) { c ->
                if (c.d("price") > 0) list.add(PriceRow(c.s("article"), c.s("name"), c.s("manufacturer"), c.s("supplier"), c.d("price"), c.s("currency"), c.s("date"), c.s("project_name"), c.s("source")))
            }
        }
        if (list.isEmpty()) {
            rows("SELECT article, name, manufacturer, supplier, price, currency, order_date, project_name FROM orders $where", args) { c ->
                val p = parseNum(c.s("price"))
                if (p > 0) list.add(PriceRow(c.s("article"), c.s("name"), c.s("manufacturer"), c.s("supplier"), p, c.s("currency"), c.s("order_date"), c.s("project_name"), "Заказ"))
            }
        }
        val groups = linkedMapOf<String, MutableList<PriceRow>>()
        for (p in list) {
            val key = p.article.trim().uppercase().ifEmpty { p.name.trim().uppercase() }
            if (key.isEmpty()) continue
            groups.getOrPut(key) { mutableListOf() }.add(p)
        }
        val out = mutableListOf<TabRecord>()
        for (key in groups.keys.sorted()) {
            val entries = groups[key] ?: continue
            val sorted = entries.sortedByDescending { parseDate(it.date)?.time ?: 0L }
            val last = sorted.first()
            val best = entries.minByOrNull { it.price } ?: last
            val prev = sorted.getOrNull(1)
            val delta = if (prev != null && prev.price > 0) (last.price - prev.price) / prev.price * 100 else null
            val arrow = if (delta != null) " · ${if (delta >= 0) "▲" else "▼"}${"%.1f".format(if (delta >= 0) delta else -delta)}%" else ""
            val sb = StringBuilder()
            sb.append("Артикул: ${last.article.ifEmpty { "—" }}\nНаименование: ${last.name}\nПроизводитель: ${last.manufacturer}\n")
            sb.append("Последняя цена: ${fmtMoney(last.price)} ${last.currency} (${last.date})\n")
            sb.append("Лучшая цена: ${fmtMoney(best.price)} ${best.currency} (${best.date})\n")
            sb.append("Записей: ${entries.size}")
            if (delta != null) sb.append("\nИзменение к предыдущей: ${"%.1f".format(delta)}%")
            sb.append("\n\nИстория:")
            for (e in sorted.take(30)) sb.append("\n• ${e.date} · ${fmtMoney(e.price)} ${e.currency} · ${e.supplier} · ${e.proj} · ${e.source}")
            out.add(TabRecord("${short(key, 25)} · ${fmtMoney(last.price)} ${last.currency}$arrow", sb.toString()))
        }
        if (out.isEmpty()) out.add(TabRecord("Нет данных", "В базе нет записей с ценами"))
        return out
    }

    // ================= ЗАКАЗЫ =================
    data class OrderBatch(
        val batchId: Int, val label: String, val orderDate: String, val project: String,
        val manufacturer: String, val subproject: String, val kd: String, val paymentDate: String,
        val deliveryDays: Int, val deliveryUnit: String, val minDate: String, val maxDate: String,
        val invoice: String, val supplier: String, val deliveryNumber: String,
        val received: Boolean, val partialReceived: Boolean, val receiptDate: String, val writeOffDate: String,
        val priceRequest: Boolean, val priceRequestNum: Int,
        val status: String, val etaDate: String, val confirmDate: String, val shipDate: String, val tracking: String
    )

    data class OrderItem(
        val id: Int, val article: String, val name: String, val nameEng: String,
        val quantity: Int, val deliveryTerm: Int, val deliveryUnit: String,
        val price: String, val currency: String, val note: String,
        val manufacturer: String, val subproject: String, val kd: String,
        val received: Boolean, val receiptDate: String, val qtyReceived: Double,
        val itemStatus: String
    ) {
        val rest: Double get() = quantity - qtyReceived
    }

    fun batchOverdue(b: OrderBatch): Boolean {
        if (b.received) return false
        val d = parseDate(b.etaDate.ifEmpty { b.maxDate }) ?: return false
        val today = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.time
        return d.before(today)
    }

    fun getDistinctProjects(): List<String> = distinctValues("project_name")
    fun getDistinctManufacturers(): List<String> = distinctValues("manufacturer")

    private fun distinctValues(column: String): List<String> {
        val list = mutableListOf("Все")
        if (!isDatabaseReady()) return list
        rows("SELECT DISTINCT $column FROM orders WHERE $column IS NOT NULL AND $column != '' ORDER BY $column") { list.add(it.s(column)) }
        return list
    }

    fun getOrderBatches(): List<OrderBatch> {
        val list = mutableListOf<OrderBatch>()
        if (!isDatabaseReady()) return list
        val opt = listOf("status" to "st", "eta_date" to "eta", "confirm_date" to "cd",
                         "ship_date" to "sd", "tracking" to "tr", "partial_received" to "part")
            .filter { columnExists("orders", it.first) }
            .joinToString("") { ", MAX(${it.first}) AS ${it.second}" }
        rows("SELECT order_batch_id AS bid, MAX(order_date) AS od, MAX(project_name) AS proj, MAX(manufacturer) AS man, MAX(subproject) AS sub, MAX(kd) AS kd, MAX(payment_date) AS pd, MAX(delivery_days) AS dd, MAX(delivery_unit_order) AS du, MAX(min_delivery_date) AS mind, MAX(max_delivery_date) AS maxd, MAX(invoice_number) AS inv, MAX(supplier) AS sup, MAX(delivery_number) AS dn, MAX(received) AS rec, MAX(receipt_date) AS rdate, MAX(write_off_date) AS wdate, MAX(price_request) AS pr, MAX(price_request_num) AS prn$opt FROM orders GROUP BY order_batch_id ORDER BY order_batch_id DESC") { c ->
            val pr = c.i("pr") == 1; val prn = c.i("prn")
            list.add(OrderBatch(
                batchId = c.i("bid"), label = if (pr && prn > 0) "Z$prn" else c.s("bid"),
                orderDate = c.s("od"), project = c.s("proj"), manufacturer = c.s("man"),
                subproject = c.s("sub"), kd = c.s("kd"), paymentDate = c.s("pd"),
                deliveryDays = c.i("dd"), deliveryUnit = c.s("du"),
                minDate = c.s("mind"), maxDate = c.s("maxd"),
                invoice = c.s("inv"), supplier = c.s("sup"), deliveryNumber = c.s("dn"),
                received = c.i("rec") == 1, partialReceived = c.i("part") == 1,
                receiptDate = c.s("rdate"), writeOffDate = c.s("wdate"),
                priceRequest = pr, priceRequestNum = prn,
                status = c.s("st"), etaDate = c.s("eta"), confirmDate = c.s("cd"),
                shipDate = c.s("sd"), tracking = c.s("tr")
            ))
        }
        return list
    }

    fun getOrderItems(batchId: Int): List<OrderItem> {
        val list = mutableListOf<OrderItem>()
        val opt = StringBuilder()
        if (columnExists("orders", "qty_received")) opt.append(", IFNULL(qty_received,0) AS qrec")
        if (columnExists("orders", "item_status")) opt.append(", item_status AS ist")
        rows("SELECT id, article, name, name_eng, quantity, delivery_term, delivery_unit, price, currency, note, manufacturer, subproject, kd, received, receipt_date$opt FROM orders WHERE order_batch_id=? ORDER BY id", arrayOf(batchId.toString())) { c ->
            list.add(OrderItem(
                id = c.i("id"), article = c.s("article"), name = c.s("name"), nameEng = c.s("name_eng"),
                quantity = c.i("quantity"), deliveryTerm = c.i("delivery_term"), deliveryUnit = c.s("delivery_unit"),
                price = c.s("price"), currency = c.s("currency"), note = c.s("note"),
                manufacturer = c.s("manufacturer"), subproject = c.s("subproject"), kd = c.s("kd"),
                received = c.i("received") == 1, receiptDate = c.s("receipt_date"), qtyReceived = c.d("qrec"),
                itemStatus = c.s("ist")
            ))
        }
        return list
    }
}