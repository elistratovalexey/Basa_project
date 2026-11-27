package com.elistratov.basaproject

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.zxing.BarcodeFormat
import com.journeyapps.barcodescanner.BarcodeEncoder
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class WarehouseActivity : AppCompatActivity() {

    private val db by lazy { DatabaseHelper(this) }
    private lateinit var mode: Spinner
    private lateinit var search: EditText
    private lateinit var list: ListView
    private lateinit var stats: TextView
    private lateinit var adapter: ArrayAdapter<String>
    private var rows: List<Map<String, String>> = emptyList()
    private var cellFilter = 0

    private val scanLauncher = registerForActivityResult(ScanContract()) { res ->
        if (res.contents != null) onBarcode(res.contents.trim())
    }
    private val camPerm = registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) launchScan() else Toast.makeText(this, "Нет разрешения на камеру", Toast.LENGTH_LONG).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val match = LinearLayout.LayoutParams.MATCH_PARENT
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(10), dp(8), dp(10), dp(8)) }

        ensureTables()

        mode = Spinner(this)
        mode.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("Позиции", "Ячейки", "Наименования")).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        root.addView(mode, LinearLayout.LayoutParams(match, wrap))
        stats = TextView(this).apply { textSize = 12f }
        root.addView(stats, LinearLayout.LayoutParams(match, wrap))

        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        search = EditText(this).apply { hint = "Поиск / штрихкод"; setSingleLine() }
        val btnScan = Button(this).apply { text = "📷" }
        val btnAdd = Button(this).apply { text = "＋" }
        row.addView(search, LinearLayout.LayoutParams(0, wrap, 1f))
        row.addView(btnScan, LinearLayout.LayoutParams(wrap, wrap))
        row.addView(btnAdd, LinearLayout.LayoutParams(wrap, wrap))
        root.addView(row, LinearLayout.LayoutParams(match, wrap))

        list = ListView(this)
        adapter = ArrayAdapter(this, android.R.layout.simple_list_item_1, mutableListOf())
        list.adapter = adapter
        root.addView(list, LinearLayout.LayoutParams(match, 0, 1f))
        setContentView(root)

        mode.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) { cellFilter = 0; reload() }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
            override fun afterTextChanged(s: Editable?) { reload() }
        })
        btnScan.setOnClickListener {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) launchScan()
            else camPerm.launch(Manifest.permission.CAMERA)
        }
        btnAdd.setOnClickListener { editDialog(null) }
        list.setOnItemClickListener { _, _, pos, _ -> editDialog(rows[pos]) }
        reload()
    }

    private fun launchScan() {
        scanLauncher.launch(ScanOptions().setPrompt("Наведите камеру на штрихкод").setBeepEnabled(true).setOrientationLocked(false))
    }

    private fun onBarcode(code: String) {
        val cell = q("SELECT id, code FROM storage_cells WHERE barcode=? OR code=?", arrayOf(code, code)).firstOrNull()
        if (cell != null) {
            cellFilter = cell["id"]!!.toInt()
            mode.setSelection(0)
            search.setText("")
            toast("Ячейка ${cell["code"]}")
            reload(); return
        }
        val item = q("SELECT id FROM warehouse_items WHERE barcode=?", arrayOf(code)).firstOrNull()
        if (item != null) {
            cellFilter = 0
            mode.setSelection(0)
            search.setText(code)
            toast("Позиция найдена по штрихкоду")
            reload(); return
        }
        search.setText(code)
        toast("Штрихкод $code не найден — поиск по тексту")
        reload()
    }

    private fun hasColumn(table: String, col: String): Boolean = try {
        db.readableDatabase.rawQuery("PRAGMA table_info($table)", null).use { c ->
            var ok = false
            while (c.moveToNext()) if (c.getString(1) == col) ok = true
            ok
        }
    } catch (e: Exception) { false }

    private fun ensureTables() {
        val w = db.writableDatabase
        w.execSQL("CREATE TABLE IF NOT EXISTS storage_cells (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, barcode TEXT UNIQUE, note TEXT DEFAULT '')")
        w.execSQL("CREATE TABLE IF NOT EXISTS warehouse_names (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, article TEXT DEFAULT '', unit TEXT DEFAULT 'шт', note TEXT DEFAULT '')")
        w.execSQL("CREATE TABLE IF NOT EXISTS warehouse_items (id INTEGER PRIMARY KEY AUTOINCREMENT, cell_id INTEGER DEFAULT 0, name TEXT DEFAULT '', qty REAL DEFAULT 0, description TEXT DEFAULT '', updated_at TEXT DEFAULT '')")
        if (!hasColumn("warehouse_items", "barcode"))
            w.execSQL("ALTER TABLE warehouse_items ADD COLUMN barcode TEXT DEFAULT ''")
        // детерминированное восстановление штрихкодов (200 — ячейки, 201 — позиции)
        for (r in q("SELECT id FROM warehouse_items WHERE barcode IS NULL OR barcode=''")) {
            val id = r["id"]!!.toInt()
            w.execSQL("UPDATE warehouse_items SET barcode=? WHERE id=?", arrayOf(ean13("201" + id.toString().padStart(9, '0')), id))
        }
        for (r in q("SELECT id FROM storage_cells WHERE barcode IS NULL OR barcode=''")) {
            val id = r["id"]!!.toInt()
            w.execSQL("UPDATE storage_cells SET barcode=? WHERE id=?", arrayOf(ean13("200" + id.toString().padStart(9, '0')), id))
        }
    }

    private fun q(sql: String, args: Array<String> = emptyArray()): List<Map<String, String>> {
        val out = mutableListOf<Map<String, String>>()
        try {
            db.readableDatabase.rawQuery(sql, args).use { c ->
                while (c.moveToNext()) {
                    val m = HashMap<String, String>()
                    for (i in 0 until c.columnCount) m[c.getColumnName(i)] = if (c.isNull(i)) "" else c.getString(i)
                    out.add(m)
                }
            }
        } catch (e: Exception) { }
        return out
    }

    private fun now() = SimpleDateFormat("dd.MM.yyyy HH:mm:ss", Locale.getDefault()).format(Date())

    private fun ean13(body12: String): String {
        val s = body12.mapIndexed { i, ch -> (ch - '0') * (if (i % 2 == 0) 1 else 3) }.sum()
        return body12 + ((10 - s % 10) % 10).toString()
    }

    private fun reload() {
        val s = search.text.toString().trim()
        val like = "%$s%"
        val m = mode.selectedItemPosition
        rows = when (m) {
            0 -> {
                var sql = "SELECT w.*, c.code AS cell_code, c.barcode AS cell_barcode FROM warehouse_items w LEFT JOIN storage_cells c ON c.id=w.cell_id WHERE 1=1"
                val a = mutableListOf<String>()
                if (cellFilter > 0) { sql += " AND w.cell_id=?"; a.add(cellFilter.toString()) }
                if (s.isNotEmpty()) { sql += " AND (w.name LIKE ? OR w.description LIKE ? OR c.code LIKE ? OR c.barcode LIKE ? OR w.barcode LIKE ?)"; repeat(5) { a.add(like) } }
                sql += " ORDER BY c.code, w.name"
                q(sql, a.toTypedArray())
            }
            1 -> if (s.isEmpty()) q("SELECT * FROM storage_cells ORDER BY code")
                 else q("SELECT * FROM storage_cells WHERE code LIKE ? OR barcode LIKE ? OR note LIKE ? ORDER BY code", arrayOf(like, like, like))
            else -> if (s.isEmpty()) q("SELECT * FROM warehouse_names ORDER BY name")
                 else q("SELECT * FROM warehouse_names WHERE name LIKE ? OR article LIKE ? ORDER BY name", arrayOf(like, like))
        }
        val titles = rows.map { r ->
            when (m) {
                0 -> "${r["cell_code"] ?: "—"} · ${r["name"]} · ${r["qty"]} ${unitFor(r["name"] ?: "")}"
                1 -> "${r["code"]} · ${r["barcode"] ?: ""}"
                else -> "${r["name"]} · ${r["article"] ?: ""} · ${r["unit"] ?: "шт"}"
            }
        }
        adapter.clear(); adapter.addAll(titles); adapter.notifyDataSetChanged()
        val st = q("SELECT COUNT(*) n, IFNULL(SUM(qty),0) q, COUNT(DISTINCT cell_id) c FROM warehouse_items").firstOrNull()
        stats.text = "Позиций ${st?.get("n") ?: 0} · всего ${st?.get("q") ?: 0} · ячеек ${st?.get("c") ?: 0} · показано ${rows.size}"
    }

    private fun unitFor(name: String): String =
        q("SELECT unit FROM warehouse_names WHERE name=?", arrayOf(name)).firstOrNull()?.get("unit") ?: "шт"

    private fun editDialog(row: Map<String, String>?) {
        val m = mode.selectedItemPosition
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val match = LinearLayout.LayoutParams.MATCH_PARENT
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT
        val form = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), 0) }
        fun field(hint: String, value: String?): EditText {
            val e = EditText(this).apply { this.hint = hint; setText(value ?: ""); setSingleLine() }
            form.addView(e, LinearLayout.LayoutParams(match, wrap))
            return e
        }
        val cells = q("SELECT id, code FROM storage_cells ORDER BY code")
        var cellSpin: Spinner? = null
        val eName: EditText; val eQty: EditText; val eDesc: EditText
        val eCode: EditText; val eNote: EditText
        val eArt: EditText; val eUnit: EditText
        when (m) {
            0 -> {
                cellSpin = Spinner(this)
                val labels = listOf("— без ячейки —") + cells.map { it["code"]!! }
                cellSpin.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, labels)
                form.addView(cellSpin)
                eName = field("Наименование", row?.get("name"))
                eQty = field("Количество", row?.get("qty"))
                eDesc = field("Описание / примечание", row?.get("description"))
                eCode = EditText(this); eNote = EditText(this); eArt = EditText(this); eUnit = EditText(this)
                if (row != null) cellSpin.setSelection(cells.indexOfFirst { it["id"] == row["cell_id"] } + 1)
            }
            1 -> {
                eCode = field("Номер ячейки", row?.get("code"))
                eNote = field("Примечание", row?.get("note"))
                eName = EditText(this); eQty = EditText(this); eDesc = EditText(this); eArt = EditText(this); eUnit = EditText(this)
            }
            else -> {
                eName = field("Наименование", row?.get("name"))
                eArt = field("Артикул", row?.get("article"))
                eUnit = field("Единица (шт/м/кг…)", row?.get("unit") ?: "шт")
                eNote = field("Примечание", row?.get("note"))
                eCode = EditText(this); eQty = EditText(this); eDesc = EditText(this)
            }
        }

        // --- Штрихкод: кнопка генерации + картинка (для ячеек и позиций) ---
        if (m != 2) {
            val bcLabel = TextView(this).apply { textSize = 14f }
            val bcImage = ImageView(this)
            val btnGen = Button(this).apply { text = "🔄 Штрихкод" }
            val bcRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            bcRow.addView(bcLabel, LinearLayout.LayoutParams(0, wrap, 1f))
            bcRow.addView(btnGen, LinearLayout.LayoutParams(wrap, wrap))
            form.addView(bcRow)
            form.addView(bcImage, LinearLayout.LayoutParams(match, dp(90)))
            fun showBc(code: String?) {
                bcLabel.text = "Штрихкод: " + (if (code.isNullOrEmpty()) "создастся при сохранении" else code)
                try {
                    bcImage.setImageBitmap(if (!code.isNullOrEmpty()) BarcodeEncoder().encodeBitmap(code, BarcodeFormat.EAN_13, 600, 180) else null)
                } catch (e: Exception) { }
            }
            showBc(row?.get("barcode"))
            btnGen.setOnClickListener {
                if (row == null) { toast("Сначала сохраните — штрихкод создастся автоматически"); return@setOnClickListener }
                val prefix = if (m == 1) "200" else "201"
                val table = if (m == 1) "storage_cells" else "warehouse_items"
                val code = ean13(prefix + row["id"]!!.toInt().toString().padStart(9, '0'))
                db.writableDatabase.execSQL("UPDATE $table SET barcode=? WHERE id=?", arrayOf(code, row["id"]))
                if (m == 0) db.writableDatabase.execSQL("UPDATE warehouse_items SET updated_at=? WHERE id=?", arrayOf(now(), row["id"]))
                showBc(code); reload()
                CloudPush.pushWarehouse(this) { _, msg -> toast(msg) }
            }
        }

        val builder = AlertDialog.Builder(this)
            .setTitle(if (row == null) "Добавить" else "Редактировать")
            .setView(form)
            .setPositiveButton("Сохранить") { _, _ ->
                val w = db.writableDatabase
                try {
                    when (m) {
                        0 -> {
                            val cid = if (cellSpin!!.selectedItemPosition > 0) cells[cellSpin.selectedItemPosition - 1]["id"]!!.toInt() else 0
                            val name = eName.text.toString().trim()
                            val qty = eQty.text.toString().replace(",", ".").toDoubleOrNull() ?: 0.0
                            val desc = eDesc.text.toString()
                            if (name.isEmpty()) { toast("Укажите наименование"); return@setPositiveButton }
                            if (row == null) {
                                w.execSQL("INSERT INTO warehouse_items (cell_id,name,qty,description,updated_at) VALUES (?,?,?,?,?)", arrayOf(cid, name, qty, desc, now()))
                                val nid = q("SELECT last_insert_rowid() AS i").first()["i"]!!.toInt()
                                w.execSQL("UPDATE warehouse_items SET barcode=? WHERE id=?", arrayOf(ean13("201" + nid.toString().padStart(9, '0')), nid))
                            } else {
                                w.execSQL("UPDATE warehouse_items SET cell_id=?,name=?,qty=?,description=?,updated_at=? WHERE id=?", arrayOf(cid, name, qty, desc, now(), row["id"]))
                            }
                        }
                        1 -> {
                            val code = eCode.text.toString().trim()
                            val note = eNote.text.toString()
                            if (code.isEmpty()) { toast("Укажите номер ячейки"); return@setPositiveButton }
                            if (row == null) {
                                w.execSQL("INSERT INTO storage_cells (code, note) VALUES (?,?)", arrayOf(code, note))
                                val id = q("SELECT last_insert_rowid() AS i").first()["i"]!!.toInt()
                                w.execSQL("UPDATE storage_cells SET barcode=? WHERE id=?", arrayOf(ean13("200" + id.toString().padStart(9, '0')), id))
                            } else w.execSQL("UPDATE storage_cells SET code=?, note=? WHERE id=?", arrayOf(code, note, row["id"]))
                        }
                        else -> {
                            val name = eName.text.toString().trim()
                            if (name.isEmpty()) { toast("Укажите наименование"); return@setPositiveButton }
                            val art = eArt.text.toString(); val unit = eUnit.text.toString().ifEmpty { "шт" }; val note = eNote.text.toString()
                            if (row == null) w.execSQL("INSERT INTO warehouse_names (name,article,unit,note) VALUES (?,?,?,?)", arrayOf(name, art, unit, note))
                            else {
                                val old = row["name"]
                                w.execSQL("UPDATE warehouse_names SET name=?,article=?,unit=?,note=? WHERE id=?", arrayOf(name, art, unit, note, row["id"]))
                                if (old != name) w.execSQL("UPDATE warehouse_items SET name=? WHERE name=?", arrayOf(name, old))
                            }
                        }
                    }
                    reload()
                    CloudPush.pushWarehouse(this) { _, msg -> toast(msg) }
                } catch (e: Exception) { toast("Ошибка: ${e.message}") }
            }
            .setNegativeButton("Отмена", null)
        if (row != null) builder.setNeutralButton("Удалить") { _, _ ->
            AlertDialog.Builder(this).setTitle("Удалить запись?").setPositiveButton("Да") { _, _ ->
                val w = db.writableDatabase
                when (m) {
                    0 -> w.execSQL("DELETE FROM warehouse_items WHERE id=?", arrayOf(row["id"]))
                    1 -> {
                        val n = q("SELECT COUNT(*) c FROM warehouse_items WHERE cell_id=?", arrayOf(row["id"]!!)).first()["c"]!!.toInt()
                        if (n > 0) { toast("В ячейке $n позиций — сначала переместите их"); return@setPositiveButton }
                        w.execSQL("DELETE FROM storage_cells WHERE id=?", arrayOf(row["id"]))
                    }
                    else -> w.execSQL("DELETE FROM warehouse_names WHERE id=?", arrayOf(row["id"]))
                }
                reload(); CloudPush.pushWarehouse(this) { _, msg -> toast(msg) }
            }.setNegativeButton("Нет", null).show()
        }
        builder.show()
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    override fun onDestroy() { super.onDestroy(); try { db.close() } catch (e: Exception) {} }
}