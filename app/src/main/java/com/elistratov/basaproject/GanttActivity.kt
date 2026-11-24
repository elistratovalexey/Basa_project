package com.elistratov.basaproject

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.os.Bundle
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

class GanttActivity : AppCompatActivity() {

    private data class Row(
        val number: Int, val name: String, val blocked: Boolean,
        val sp: Date?, val ep: Date?, val sf: Date?, val ef: Date?,
        val bs: Date?, val be: Date?, val light: String
    )

    private lateinit var spinner: Spinner
    private lateinit var vScroll: ScrollView
    private lateinit var info: TextView
    private var projects: List<String> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }
        val match = LinearLayout.LayoutParams.MATCH_PARENT
        val wrap = LinearLayout.LayoutParams.WRAP_CONTENT
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), dp(8), dp(8), dp(8)) }

        spinner = Spinner(this)
        root.addView(spinner, LinearLayout.LayoutParams(match, wrap))
        info = TextView(this).apply { textSize = 12f }
        root.addView(info, LinearLayout.LayoutParams(match, wrap))

        val hScroll = HorizontalScrollView(this)
        vScroll = ScrollView(this)
        hScroll.addView(vScroll, ViewGroup.LayoutParams(match, match))
        root.addView(hScroll, LinearLayout.LayoutParams(match, 0, 1f))
        setContentView(root)

        val db = DatabaseHelper(this)
        projects = if (db.isDatabaseReady()) db.getProjectNames() else emptyList()
        if (projects.isEmpty()) {
            info.text = "База не загружена или нет проектов. Синхронизируйте базу на главном экране."
            spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, listOf("—"))
            return
        }
        spinner.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, projects).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        val saved = getSharedPreferences("app_settings", MODE_PRIVATE).getString("selected_project", projects[0])
        val idx = projects.indexOf(saved).coerceAtLeast(0)
        spinner.setSelection(idx)
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, pos: Int, id: Long) { showProject(projects[pos]) }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        showProject(projects[idx])
    }

    private fun pd(s: String?): Date? {
        if (s.isNullOrBlank()) return null
        for (f in listOf("dd.MM.yyyy", "dd.MM.yy", "yyyy-MM-dd")) {
            try {
                val sdf = SimpleDateFormat(f, Locale.getDefault()); sdf.isLenient = false
                return sdf.parse(s.trim())
            } catch (e: Exception) { }
        }
        return null
    }

    private fun days(a: Date, b: Date): Int = ((a.time - b.time) / 86400000L).toInt()

    private fun loadRows(project: String): List<Row> {
        val db = DatabaseHelper(this)
        if (!db.isDatabaseReady()) return emptyList()
        var pid = -1
        try {
            db.readableDatabase.rawQuery("SELECT id FROM projects WHERE name=?", arrayOf(project))
                .use { c -> if (c.moveToFirst()) pid = c.getInt(0) }
        } catch (e: Exception) { return emptyList() }
        if (pid < 0) return emptyList()
        val cols = HashSet<String>()
        try {
            db.readableDatabase.rawQuery("PRAGMA table_info(plan_fact)", null)
                .use { c -> while (c.moveToNext()) cols.add(c.getString(1)) }
        } catch (e: Exception) { return emptyList() }
        if (!cols.contains("number")) return emptyList()
        val opt = listOf("start_plan", "end_plan", "start_fact", "end_fact", "baseline_start", "baseline_end", "is_blocked")
            .filter { cols.contains(it) }.joinToString("") { ", $it" }
        val out = mutableListOf<Row>()
        val today = Calendar.getInstance().apply {
            set(Calendar.HOUR_OF_DAY, 0); set(Calendar.MINUTE, 0); set(Calendar.SECOND, 0); set(Calendar.MILLISECOND, 0)
        }.time
        try {
            db.readableDatabase.rawQuery("SELECT number, name, status$opt FROM plan_fact WHERE project_id=? ORDER BY number", arrayOf(pid.toString())).use { c ->
                fun s(col: String): String { val i = c.getColumnIndex(col); return if (i >= 0 && !c.isNull(i)) c.getString(i) else "" }
                fun i(col: String): Int { val idx = c.getColumnIndex(col); return if (idx >= 0 && !c.isNull(idx)) c.getInt(idx) else 0 }
                while (c.moveToNext()) {
                    val sp = pd(s("start_plan")); val ep = pd(s("end_plan"))
                    val sf = pd(s("start_fact")); val ef = pd(s("end_fact"))
                    val blocked = i("is_blocked") == 1
                    val done = s("status") == "Выполнено" || s("status") == "Завершено"
                    val delta = when {
                        ef != null && ep != null -> days(ef, ep)
                        ep != null && !done -> days(today, ep)
                        done -> 0
                        else -> null
                    }
                    val light = when {
                        done -> "done"
                        blocked -> "blocked"
                        delta != null && delta > 0 -> "overdue"
                        ep != null && days(ep, today) in 0..3 -> "soon"
                        else -> "ok"
                    }
                    out.add(Row(i("number"), s("name"), blocked, sp, ep, sf, ef, pd(s("baseline_start")), pd(s("baseline_end")), light))
                }
            }
        } catch (e: Exception) { }
        return out
    }

    private fun showProject(project: String) {
        vScroll.removeAllViews()
        val rows = loadRows(project)
        val dates = rows.flatMap { listOfNotNull(it.sp, it.ep, it.sf, it.ef, it.bs, it.be) }
        if (rows.isEmpty() || dates.isEmpty()) {
            info.text = "Нет дат для отображения (проект: $project)"
            return
        }
        val d0 = dates.minOrNull()!!
        val d1 = maxOf(dates.maxOrNull()!!, Date())
        val span = days(d1, d0) + 1
        info.text = "$project · работ ${rows.size} · серая—база, синяя—план, цветная—факт, красная—сегодня"
        vScroll.addView(GanttView(this, rows, d0, span), ViewGroup.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT))
    }

    private inner class GanttView(ctx: Context, private val rows: List<Row>, private val d0: Date, private val span: Int) : View(ctx) {
        private val dens = resources.displayMetrics.density
        private val scale = (dens * 14).toInt().coerceAtLeast(10)
        private val rowH = (dens * 30).toInt()
        private val leftPad = (dens * 150).toInt()
        private val topPad = (dens * 36).toInt()
        private val contentW = leftPad + span * scale + (dens * 16).toInt()
        private val contentH = topPad + rows.size * rowH + (dens * 16).toInt()
        private val grid = Paint().apply { color = 0xFFEEEEEE.toInt(); strokeWidth = 1f }
        private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF202124.toInt(); textSize = dens * 11 }
        private val small = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = 0xFF666666.toInt(); textSize = dens * 9 }
        private val todayP = Paint().apply { color = Color.RED; strokeWidth = dens * 1.5f; pathEffect = DashPathEffect(floatArrayOf(8f, 6f), 0f) }
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG)
        private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE; strokeWidth = 1f }
        private val df = SimpleDateFormat("dd.MM", Locale.getDefault())

        private fun dx(d: Date): Int = days(d, d0)

        override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
            setMeasuredDimension(contentW, contentH)
        }

        private fun bar(canvas: Canvas, s: Date, e: Date, y1: Float, y2: Float, fillColor: Int, strokeColor: Int?) {
            val x1 = (leftPad + dx(s) * scale).toFloat()
            val x2 = (leftPad + (dx(e) + 1) * scale).toFloat().coerceAtLeast(x1 + dens)
            fill.color = fillColor
            canvas.drawRect(x1, y1, x2, y2, fill)
            if (strokeColor != null) { stroke.color = strokeColor; canvas.drawRect(x1, y1, x2, y2, stroke) }
        }

        override fun onDraw(canvas: Canvas) {
            canvas.drawColor(Color.WHITE)
            val bottom = (topPad + rows.size * rowH).toFloat()
            var i = 0
            while (i < span) {
                val x = (leftPad + i * scale).toFloat()
                canvas.drawLine(x, topPad - dens * 8, x, bottom, grid)
                canvas.drawText(df.format(Date(d0.time + i * 86400000L)), x + 2, topPad - dens * 12, small)
                i += 7
            }
            val now = Date()
            val tx = (leftPad + dx(now) * scale).toFloat()
            if (tx >= leftPad && tx <= contentW) canvas.drawLine(tx, topPad - dens * 8, tx, bottom, todayP)
            for ((idx, r) in rows.withIndex()) {
                val y = topPad + idx * rowH
                val mark = if (r.blocked) "🔒 " else ""
                canvas.drawText("$mark№${r.number} ${r.name.take(20)}", dens * 4, y + rowH * 0.62f, label)
                if (r.bs != null && r.be != null) bar(canvas, r.bs, r.be, y.toFloat(), y + dens * 4, 0xFFCCCCCC.toInt(), null)
                if (r.sp != null && r.ep != null) bar(canvas, r.sp, r.ep, y + dens * 6, y + dens * 15, 0xFFCFE2F3.toInt(), 0xFF3D85C6.toInt())
                if (r.sf != null) {
                    val e = r.ef ?: now
                    val c = when (r.light) {
                        "done" -> 0xFFB6D7A8.toInt(); "overdue" -> 0xFFEA9999.toInt()
                        "blocked" -> 0xFFD9D2E9.toInt(); else -> 0xFFFFD966.toInt()
                    }
                    bar(canvas, r.sf, e, y + dens * 17, y + dens * 25, c, 0xFF999999.toInt())
                }
            }
        }
    }
}