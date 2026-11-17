package com.elistratov.basaproject

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

class DatabaseHelper(context: Context) : SQLiteOpenHelper(context, "projects.db", null, 1) {
    override fun onCreate(db: SQLiteDatabase?) {}
    override fun onUpgrade(db: SQLiteDatabase?, oldVersion: Int, newVersion: Int) {}

    fun getDistinctProjects(): List<String> {
        val list = mutableListOf("Все")
        readableDatabase.rawQuery("SELECT DISTINCT project_name FROM orders WHERE project_name IS NOT NULL", null).use { c ->
            while (c.moveToNext()) list.add(c.getString(0))
        }
        return list
    }

    fun getDistinctManufacturers(): List<String> {
        val list = mutableListOf("Все")
        readableDatabase.rawQuery("SELECT DISTINCT manufacturer FROM orders WHERE manufacturer IS NOT NULL", null).use { c ->
            while (c.moveToNext()) list.add(c.getString(0))
        }
        return list
    }

    fun getOrders(project: String?, isReceived: Boolean?, manufacturer: String?): List<Order> {
        val orders = mutableListOf<Order>()
        val query = StringBuilder("SELECT id, project_name, manufacturer, article, name, quantity, total_price, is_received FROM orders WHERE 1=1")
        val args = mutableListOf<String>()

        if (!project.isNullOrEmpty() && project != "Все") { query.append(" AND project_name = ?"); args.add(project) }
        if (isReceived != null) { query.append(" AND is_received = ?"); args.add(if (isReceived) "1" else "0") }
        if (!manufacturer.isNullOrEmpty() && manufacturer != "Все") { query.append(" AND manufacturer LIKE ?"); args.add("%$manufacturer%") }

        readableDatabase.rawQuery(query.toString(), args.toTypedArray()).use { c ->
            while (c.moveToNext()) {
                orders.add(Order(c.getInt(0), c.getString(1) ?: "", c.getString(2) ?: "", c.getString(3) ?: "", c.getString(4) ?: "", c.getDouble(5), c.getDouble(6), c.getInt(7) == 1))
            }
        }
        return orders
    }

    data class Order(val id: Int, val project: String, val manufacturer: String, val article: String, val name: String, val quantity: Double, val total: Double, val isReceived: Boolean)
}