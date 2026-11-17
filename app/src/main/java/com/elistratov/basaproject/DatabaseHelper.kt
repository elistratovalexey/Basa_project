package com.elistratov.basaproject

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class DatabaseHelper(private val context: Context) : SQLiteOpenHelper(context, "projects.db", null, 1) {

    override fun onCreate(db: SQLiteDatabase?) {}
    override fun onUpgrade(db: SQLiteDatabase?, oldVersion: Int, newVersion: Int) {}

    /** База загружена и содержит таблицу orders? */
    fun isDatabaseReady(): Boolean {
        val f = context.getDatabasePath("projects.db")
        if (!f.exists() || f.length() < 100) return false
        return try {
            readableDatabase.rawQuery(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='orders'", null
            ).use { it.moveToFirst() }
        } catch (e: Exception) { false }
    }

    fun getDistinctProjects(): List<String> = distinctValues("project_name")
    fun getDistinctManufacturers(): List<String> = distinctValues("manufacturer")

    private fun distinctValues(column: String): List<String> {
        val list = mutableListOf("Все")
        if (!isDatabaseReady()) return list
        try {
            readableDatabase.rawQuery(
                "SELECT DISTINCT $column FROM orders WHERE $column IS NOT NULL AND $column != '' ORDER BY $column", null
            ).use { c -> while (c.moveToNext()) list.add(c.getString(0)) }
        } catch (e: Exception) { }
        return list
    }

    fun getOrders(project: String?, isReceived: Boolean?, manufacturer: String?): List<Order> {
        val orders = mutableListOf<Order>()
        if (!isDatabaseReady()) return orders
        val query = StringBuilder(
            "SELECT id, order_batch_id, project_name, manufacturer, article, name, " +
            "quantity, price, currency, received, supplier, order_date FROM orders WHERE 1=1"
        )
        val args = mutableListOf<String>()
        if (!project.isNullOrEmpty() && project != "Все") { query.append(" AND project_name = ?"); args.add(project) }
        if (isReceived != null) { query.append(" AND received = ?"); args.add(if (isReceived) "1" else "0") }
        if (!manufacturer.isNullOrEmpty() && manufacturer != "Все") { query.append(" AND manufacturer LIKE ?"); args.add("%$manufacturer%") }
        query.append(" ORDER BY order_batch_id DESC, id")
        try {
            readableDatabase.rawQuery(query.toString(), args.toTypedArray()).use { c ->
                while (c.moveToNext()) {
                    val price = (c.getString(7) ?: "").replace(',', '.').replace(" ", "").toDoubleOrNull() ?: 0.0
                    orders.add(Order(
                        id = c.getInt(0), batchId = c.getInt(1),
                        project = c.getString(2) ?: "", manufacturer = c.getString(3) ?: "",
                        article = c.getString(4) ?: "", name = c.getString(5) ?: "",
                        quantity = c.getInt(6), price = price,
                        currency = c.getString(8) ?: "", received = c.getInt(9) == 1,
                        supplier = c.getString(10) ?: "", orderDate = c.getString(11) ?: ""
                    ))
                }
            }
        } catch (e: Exception) { }
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