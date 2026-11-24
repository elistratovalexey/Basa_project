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

    // ================= ПЛАН-ФАКТ v3 =================
    private data class PfWork(
        val id: Int, val number: Int, val name: String, val workType: String, val status: String, val note: String,
        val subproject: String, val responsible: String, val startPlan: String, val startFact: String,
        val dur: Double, val unit: String, val endPlan: String, val endFact: String, val comment: String,
        val progress: Int, val milestone: Boolean, val baseStart: String, val baseEnd: String,
        val blocked: Boolean, val reason: String, val blockedNote: String, val cost: Double,
        val linkBatch: Int, val autoDates: Boolean, val notifyDays: Int
    )

    private fun pfOrderDates(batchId: Int): String {
        var eta = ""; var confirm = ""; var maxd = ""; var pay = ""; var od = ""
        val opt = listOf("eta_date" to "eta", "confirm_date" to "cd").filter { columnExists("orders", it.first) }
            .joinToString("") { ", MAX(${it.first}) AS ${it.second}" }
        rows("SELECT MAX(max_delivery_date) AS maxd, MAX(payment_date) AS pd, MAX(order_date) AS od$opt FROM orders WHERE order_batch_id=?", arrayOf(batchId.toString())) { c ->
            eta = c.s("eta"); confirm = c.s("cd"); maxd = c.s("maxd"); pay = c.s("pd"); od = c.s("od")
        }
        val end = eta.ifEmpty { maxd }
        val start = confirm.ifEmpty { pay.ifEmpty { od } }
        return "начало ${start.ifEmpty { "—" }} → окончание ${end.ifEmpty { "—" }}"
    }

    private fun planFact(project: String?): List<TabRecord> {
        if (!tableExists("plan_fact")) return listOf(TabRecord("Нет данных", "Таблица «План-Факт» отсутствует в базе"))
        val out = mutableListOf<TabRecord>()
        val today = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.time

        if (tableExists("responsibles")) {
            val sb = StringBuilder("База ответственных:")
            var cnt = 0
            rows("SELECT name, position, email, phone FROM responsibles ORDER BY name") { c ->
                cnt++
                sb.append("\n\n• ${c.s("name")}")
                if (c.s("position").isNotEmpty()) sb.append(" · ${c.s("position")}")
                if (c.s("phone").isNotEmpty()) sb.append("\n  тел: ${c.s("phone")}")
                if (c.s("email").isNotEmpty()) sb.append("\n  e-mail: ${c.s("email")}")
            }
            if (cnt > 0) out.add(TabRecord("👥 База ответственных ($cnt)", sb.toString()))
        }
        if (tableExists("delay_reasons")) {
            val sb = StringBuilder("Справочник причин задержек:")
            var cnt = 0
            rows("SELECT name FROM delay_reasons ORDER BY name") { c -> cnt++; sb.append("\n• ${c.s("name")}") }
            if (cnt > 0) out.add(TabRecord("📋 Причины задержек ($cnt)", sb.toString()))
        }

        val pfCols = listOf("subproject", "responsible", "start_plan", "start_fact", "duration_qty",
            "duration_unit", "end_plan", "end_fact", "comment", "progress", "is_milestone",
            "baseline_start", "baseline_end", "is_blocked", "delay_reason", "blocked_note",
            "cost_weight", "link_order_batch", "auto_dates", "notify_days")
        val projects = if (project != null) listOf(project) else getProjectNames()
        for (name in projects) {
            val pid = projectId(name) ?: continue
            val extra = pfCols.filter { columnExists("plan_fact", it) }.joinToString("") { ", $it" }
            val works = mutableListOf<PfWork>()
            rows("SELECT id, number, name, work_type, status, note$extra FROM plan_fact WHERE project_id=? ORDER BY number", arrayOf(pid.toString())) { c ->
                val nd = c.i("notify_days")
                works.add(PfWork(
                    c.i("id"), c.i("number"), c.s("name"), c.s("work_type"), c.s("status"), c.s("note"),
                    c.s("subproject"), c.s("responsible"), c.s("start_plan"), c.s("start_fact"),
                    c.d("duration_qty"), c.s("duration_unit").ifEmpty { "Календарные дни" },
                    c.s("end_plan"), c.s("end_fact"), c.s("comment"), c.i("progress"), c.i("is_milestone") == 1,
                    c.s("baseline_start"), c.s("baseline_end"), c.i("is_blocked") == 1, c.s("delay_reason"),
                    c.s("blocked_note"), c.d("cost_weight"), c.i("link_order_batch"), c.i("auto_dates") == 1,
                    if (nd > 0) nd else 3
                ))
            }
            if (works.isEmpty()) continue
            val byId = works.associateBy { it.id }
            val preds = HashMap<Int, MutableList<Pair<Int, String>>>()
            val succ = HashMap<Int, MutableList<Int>>()
            if (tableExists("plan_fact_links")) {
                rows("SELECT work_id, depends_on, link_type FROM plan_fact_links WHERE project_id=?", arrayOf(pid.toString())) { c ->
                    val w = c.i("work_id"); val d = c.i("depends_on")
                    preds.getOrPut(w) { mutableListOf() }.add(Pair(d, c.s("link_type")))
                    succ.getOrPut(d) { mutableListOf() }.add(w)
                }
            }
            val projEnd = works.mapNotNull { parseDate(it.endPlan) }.maxOrNull()
            var totalW = 0.0; var doneW = 0.0; var costW = 0.0; var doneCostW = 0.0
            var nDone = 0; var nInWork = 0; var nOverdue = 0; var nLate = 0; var nCrit = 0; var nBlocked = 0
            var maxBaseShift = 0
            class Acc { var works = 0; var days = 0.0; var overdue = 0; var blocked = 0; val iv = mutableListOf<Pair<Long, Long>>() }
            val workload = HashMap<String, Acc>()
            val delays = HashMap<String, IntArray>()
            val delayNums = HashMap<String, MutableList<String>>()
            val notes = mutableListOf<Triple<Int, Int, String>>()
            val recs = mutableListOf<TabRecord>()
            for (w in works) {
                val sp = parseDate(w.startPlan); val sf = parseDate(w.startFact)
                val ep = parseDate(w.endPlan); val ef = parseDate(w.endFact)
                val be = parseDate(w.baseEnd)
                val done = w.status in listOf("Выполнено", "Завершено")
                var prog = w.progress; if (done) prog = 100
                val weight = if (w.dur > 0) w.dur else 1.0
                totalW += weight; doneW += weight * prog / 100.0
                if (w.cost > 0) { costW += w.cost; doneCostW += w.cost * prog / 100.0 }
                val delta = when {
                    ef != null && ep != null -> daysBetween(ef, ep)
                    ep != null && !done -> daysBetween(today, ep)
                    done -> 0
                    else -> null
                }
                val baseShift = if (ep != null && be != null) daysBetween(ep, be) else null
                if (baseShift != null && baseShift > maxBaseShift) maxBaseShift = baseShift
                val forecast = if (sf != null && !done) calcDeadline(w.startFact, w.dur.toInt().toString(), w.unit) else ""
                val lateStart = sp != null && sf == null && sp.before(today) && !done
                var slack: Int? = null
                if (ep != null) {
                    val ss = succ[w.id]?.mapNotNull { byId[it]?.let { s -> parseDate(s.startPlan) } } ?: emptyList()
                    slack = if (ss.isNotEmpty()) daysBetween(ss.minOrNull()!!, ep) - 1
                            else if (projEnd != null) daysBetween(projEnd, ep) else null
                }
                val critical = slack != null && slack <= 0 && !done
                val light = when {
                    done -> "done"
                    w.blocked -> "blocked"
                    delta != null && delta > 0 -> "overdue"
                    ep != null && daysBetween(ep, today) in 0..3 -> "soon"
                    else -> "ok"
                }
                val color = when (light) {
                    "done" -> 0xFFD9EAD3L; "blocked" -> 0xFFD9D2E9L
                    "overdue" -> 0xFFF4CCCCL; "soon" -> 0xFFFFF2CCL; else -> 0L
                }
                val depends = preds[w.id]?.mapNotNull { l -> byId[l.first]?.let { "№${it.number}(${l.second})" } }
                    ?.joinToString(", ") ?: "—"
                if (done) nDone++; if (!done && sf != null) nInWork++
                if (light == "overdue") nOverdue++; if (lateStart) nLate++
                if (critical) nCrit++; if (w.blocked) nBlocked++
                val rk = w.responsible.ifEmpty { "— не назначен —" }
                if (!done) {
                    val a = workload.getOrPut(rk) { Acc() }
                    a.works++; a.days += if (w.unit == "Недели") w.dur * 7 else w.dur
                    if (light == "overdue") a.overdue++; if (w.blocked) a.blocked++
                    if (sp != null && ep != null) a.iv.add(sp.time to ep.time)
                }
                if (w.blocked || light == "overdue" || lateStart) {
                    val rs = w.reason.ifEmpty { "— причина не указана —" }
                    val dl = delays.getOrPut(rs) { IntArray(2) }
                    dl[0]++; dl[1] += (delta ?: 0).coerceAtLeast(0)
                    delayNums.getOrPut(rs) { mutableListOf() }.add(w.number.toString())
                }
                if (!done) {
                    if (w.blocked) notes.add(Triple(2, 0, "🔒 №${w.number} ${w.name}: заблокирована — ${w.reason.ifEmpty { "причина не указана" }}"))
                    if (sp != null && w.startFact.isEmpty()) {
                        val d = daysBetween(sp, today)
                        if (d < 0) notes.add(Triple(1, -d, "№${w.number} ${w.name}: старт просрочен на ${-d} дн (план ${w.startPlan})"))
                        else if (d <= 1) notes.add(Triple(4, d, "№${w.number} ${w.name}: старт ${if (d == 0) "сегодня" else "завтра"}"))
                    }
                    if (ep != null) {
                        val d = daysBetween(ep, today)
                        if (d < 0) notes.add(Triple(0, -d, "🔴 №${w.number} ${w.name}: ПРОСРОЧКА ${-d} дн (дедлайн ${w.endPlan})"))
                        else if (d <= w.notifyDays) notes.add(Triple(3, d, "№${w.number} ${w.name}: дедлайн через $d дн (${w.endPlan})"))
                    }
                }
                val marks = (if (w.blocked) "🔒 " else "") + (if (critical) "★ " else "") + (if (w.milestone) "⚑ " else "")
                val det = buildString {
                    append("Проект: $name\nРабота №${w.number}: ${w.name}\n")
                    append("Подпроект: ${w.subproject.ifEmpty { "—" }}\nТип: ${w.workType.ifEmpty { "—" }}\n")
                    append("Ответственный: ${w.responsible.ifEmpty { "—" }}\nСтатус: ${w.status}\n")
                    append("Начало план: ${w.startPlan.ifEmpty { "—" }}\nНачало факт: ${w.startFact.ifEmpty { "—" }}\n")
                    append("Выполнение: ${fmtMoney(w.dur)} ${w.unit}\n")
                    append("Окончание план: ${w.endPlan.ifEmpty { "—" }}\nОкончание факт: ${w.endFact.ifEmpty { "—" }}\n")
                    append("Готовность: $prog%\n")
                    if (delta != null) append("Отклонение: $delta дн.\n")
                    if (baseShift != null) append("Сдвиг базового плана: $baseShift дн.\n")
                    if (forecast.isNotEmpty()) append("Прогноз окончания: $forecast\n")
                    if (slack != null) append("Резерв: $slack дн.${if (critical) " ★ критическая" else ""}\n")
                    if (lateStart) append("⚠ Начало просрочено\n")
                    append("Зависит от: $depends\n")
                    if (w.baseStart.isNotEmpty()) append("Базовый план: ${w.baseStart} → ${w.baseEnd}\n")
                    if (w.blocked) {
                        append("🔒 Заблокирована: ${w.reason.ifEmpty { "причина не указана" }}\n")
                        if (w.blockedNote.isNotEmpty()) append("Примечание к блокировке: ${w.blockedNote}\n")
                    }
                    if (w.linkBatch > 0) {
                        append("Связан заказ: №${w.linkBatch} (${pfOrderDates(w.linkBatch)})\n")
                        if (w.autoDates) append("Автодаты из заказа: включены\n")
                    }
                    append("Уведомлять за: ${w.notifyDays} дн.\n")
                    if (w.cost > 0) append("Стоимость: ${fmtMoney(w.cost)} ₽\n")
                    if (w.comment.isNotEmpty()) append("Комментарии: ${w.comment}\n")
                    if (w.note.isNotEmpty()) append("Примечание: ${w.note}\n")
                }
                recs.add(TabRecord("$marks№${w.number} · ${short(w.name, 30)} · ${w.status} · $prog%", det, color))
            }
            val progress = if (totalW > 0) Math.round(doneW / totalW * 1000) / 10.0 else 0.0
            val progressCost = if (costW > 0) Math.round(doneCostW / costW * 1000) / 10.0 else progress
            out.add(TabRecord("📊 $name · готовность $progress%",
                "Проект: $name\nВсего работ: ${works.size}\nВыполнено: $nDone\nВ работе: $nInWork\nПросрочено: $nOverdue\nПросрочено начало: $nLate\nКритических: $nCrit\nЗаблокировано: $nBlocked\nГотовность (по длительности): $progress%\nГотовность (по стоимости): $progressCost%\nМакс. сдвиг базового плана: $maxBaseShift дн.",
                if (nOverdue > 0 || nBlocked > 0) 0xFFF4CCCCL else 0xFFD9EAD3L))
            out.addAll(recs)
            if (notes.isNotEmpty()) {
                val sb = StringBuilder("Уведомления · $name:")
                for (n in notes.sortedWith(compareBy({ it.first }, { -it.second }))) sb.append("\n\n${n.third}")
                out.add(TabRecord("🔔 Уведомления · $name (${notes.size})", sb.toString(), 0xFFF4CCCCL))
            }
            if (workload.isNotEmpty()) {
                val sb = StringBuilder("Загрузка ответственных · $name:")
                val items = workload.map { (rn, a) ->
                    val events = mutableListOf<Pair<Long, Int>>()
                    for ((s, e) in a.iv) { events.add(s to 1); events.add(e to -1) }
                    events.sortBy { it.first }
                    var cur = 0; var peak = 0
                    for ((_, d) in events) { cur += d; if (cur > peak) peak = cur }
                    val overload = peak > 3 || a.days > 60
                    Triple(rn, a, peak to overload)
                }.sortedWith(compareByDescending { it.third.second })
                for ((rn, a, po) in items) {
                    sb.append("\n\n• $rn${if (po.second) " ⚠ ПЕРЕГРУЗ" else ""}\n  работ ${a.works} · дней ${fmtMoney(a.days)} · просрочено ${a.overdue} · блокировано ${a.blocked} · пик параллельных ${po.first}")
                }
                out.add(TabRecord("👷 Загрузка · $name", sb.toString()))
            }
            if (delays.isNotEmpty()) {
                val sb = StringBuilder("Аналитика задержек · $name:")
                for ((rs, v) in delays.entries.sortedByDescending { it.value[1] }) {
                    sb.append("\n\n• $rs\n  работ ${v[0]} · дней просрочки ${v[1]} · № ${delayNums[rs]?.joinToString(", ") ?: ""}")
                }
                out.add(TabRecord("⏱ Задержки · $name", sb.toString()))
            }
            if (tableExists("plan_fact_audit")) {
                val sb = StringBuilder("История изменений · $name:")
                var cnt = 0
                rows("SELECT ts, number, field, old_value, new_value, author, device FROM plan_fact_audit WHERE project_id=? ORDER BY id DESC LIMIT 60", arrayOf(pid.toString())) { c ->
                    cnt++
                    sb.append("\n\n${c.s("ts")} · №${c.i("number")} · ${c.s("field")}\n  ${c.s("old_value").ifEmpty { "—" }} → ${c.s("new_value").ifEmpty { "—" }}\n  кто: ${c.s("author").ifEmpty { c.s("device") }}")
                }
                if (cnt > 0) out.add(TabRecord("📜 История изменений · $name ($cnt)", sb.toString()))
            }
        }
        if (out.isEmpty()) out.add(TabRecord("Нет данных", "В проектах нет работ План-Факт"))
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
            val pid = projectId(name) ?: continue
            val coef = getOrdersCostCoef(name)
            var planSell = 0.0; var income = 0.0
            var pbo = 0.0; var obs = 0.0; var pbs = 0.0; var recv = 0.0
            var paidSup = 0.0; var byFlag = 0.0; var unmarked = 0.0
            val detail = StringBuilder()
            rows("SELECT number, name, quantity, price, currency FROM specifications WHERE project_id=?", arrayOf(pid.toString())) { c ->
                val v = parseNum(c.s("quantity")) * parseNum(c.s("price")); val rv = v * getRate(c.s("currency")); planSell += rv
                detail.append("\n[План] ${c.s("name")} · ${fmtMoney(rv)} ₽")
            }
            rows("SELECT number, amount, currency, paid FROM payments WHERE project_id=?", arrayOf(pid.toString())) { c ->
                if (c.i("paid") == 1) {
                    val v = parseNum(c.s("amount")); val rv = v * getRate(c.s("currency")); income += rv
                    detail.append("\n[Клиент] платёж №${c.i("number")} · ${fmtMoney(rv)} ₽")
                }
            }
            rows("SELECT order_batch_id, article, name, quantity, price, currency, received FROM orders WHERE project_name=?", arrayOf(name)) { c ->
                val base = c.i("quantity") * parseNum(c.s("price")); val r = getRate(c.s("currency"))
                obs += base * r; val v = base * coef * r; pbo += v
                if (c.i("received") == 1) recv += v
                detail.append("\n[Заказ] №${c.i("order_batch_id")} ${c.s("article").ifEmpty { c.s("name") }} ×${fmtMoney(coef)} · ${fmtMoney(v)} ₽")
            }
            rows("SELECT id, supplier, name, total, quantity, price, currency, received FROM purchase_specifications WHERE project_id=?", arrayOf(pid.toString())) { c ->
                val sid = c.i("id"); val r = getRate(c.s("currency")); val isRec = c.i("received") == 1
                var base = c.d("total"); if (base <= 0) base = c.d("quantity") * c.d("price")
                if (base > 0) {
                    val rv = base * r; pbs += rv; if (isRec) recv += rv
                    detail.append("\n[Счёт] ${c.s("supplier")} · ${fmtMoney(rv)} ₽")
                } else {
                    rows("SELECT name, total, quantity, price FROM purchase_spec_items WHERE spec_id=?", arrayOf(sid.toString())) { it2 ->
                        var iv = it2.d("total"); if (iv <= 0) iv = it2.d("quantity") * it2.d("price")
                        if (iv > 0) {
                            val rv = iv * r; pbs += rv; if (isRec) recv += rv
                            detail.append("\n[Счёт] ${c.s("supplier")} · ${it2.s("name")} · ${fmtMoney(rv)} ₽")
                        }
                    }
                }
            }
            rows("SELECT pp.number, pp.amount, pp.currency, pp.paid, pp.spec_id, s.supplier FROM purchase_payments pp JOIN purchase_specifications s ON s.id=pp.spec_id WHERE s.project_id=?", arrayOf(pid.toString())) { c ->
                val v = parseNum(c.s("amount"))
                if (v > 0) {
                    val rv = v * getRate(c.s("currency")); paidSup += rv
                    if (c.i("paid") == 1) byFlag += rv else unmarked += rv
                    val mk = if (c.i("paid") == 1) "" else " (не отмечен)"
                    detail.append("\n[Поставщик] ${c.s("supplier")} счёт №${c.i("spec_id")} платёж №${c.i("number")}$mk · ${fmtMoney(rv)} ₽")
                }
            }
            val planBuy = pbo + pbs; val balance = income - paidSup; val markup = pbo - obs
            out.add(TabRecord("$name · баланс: ${fmtMoney(balance)} ₽",
                "Проект: $name\nКоэффициент заказов: ×${fmtMoney(coef)}\n\n" +
                    "План продажи: ${fmtMoney(planSell)} ₽\nОплачено клиентом: ${fmtMoney(income)} ₽\n\n" +
                    "Закупки (план, всего): ${fmtMoney(planBuy)} ₽\n  в т.ч. заказы (×${fmtMoney(coef)}): ${fmtMoney(pbo)} ₽\n  в т.ч. счета поставщиков: ${fmtMoney(pbs)} ₽\n  наценка: ${fmtMoney(markup)} ₽\n\n" +
                    "Оплачено поставщикам (по сумме): ${fmtMoney(paidSup)} ₽\n  отмечено «Оплачен»: ${fmtMoney(byFlag)} ₽\n  не отмечено: ${fmtMoney(unmarked)} ₽\n" +
                    "Баланс (клиент − поставщики): ${fmtMoney(balance)} ₽\n\n" +
                    "Получено (закупки): ${fmtMoney(recv)} ₽\nМаржа план: ${fmtMoney(planSell - planBuy)} ₽\nМаржа факт: ${fmtMoney(balance)} ₽\n\nРасшифровка:$detail",
                if (balance >= 0) 0xFFD9EAD3L else 0xFFF4CCCCL))
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