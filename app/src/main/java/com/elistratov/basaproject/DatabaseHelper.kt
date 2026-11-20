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
