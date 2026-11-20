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
