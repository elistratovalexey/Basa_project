package com.elistratov.basaproject

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import java.io.File
import java.text.SimpleDateFormat
import java.util.Locale

object MailHelper {

    private fun mailFile(context: Context): File = context.getDatabasePath("mail.db")

    private fun open(context: Context): SQLiteDatabase? {
        val f = mailFile(context)
        if (!f.exists() || f.length() < 100) return null
        return try {
            val db = SQLiteDatabase.openDatabase(f.absolutePath, null, SQLiteDatabase.OPEN_READONLY)
            val ok = db.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'", null)
                .use { it.moveToFirst() }
            if (ok) db else { db.close(); null }
        } catch (e: Exception) { null }
    }

    private fun Cursor.s(col: String): String { val i = getColumnIndex(col); return if (i >= 0 && !isNull(i)) getString(i) else "" }
    private fun Cursor.i(col: String): Int { val i = getColumnIndex(col); return if (i >= 0 && !isNull(i)) getInt(i) else 0 }

    private fun pd(s: String?): Long {
        if (s.isNullOrBlank()) return 0L
        return try {
            SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(s.trim().take(10))?.time ?: 0L
        } catch (e: Exception) { 0L }
    }

    private fun short(s: String, n: Int) = if (s.length > n) s.take(n) + "…" else s

    fun records(context: Context, project: String?, search: String): List<DatabaseHelper.TabRecord> {
        val db = open(context) ?: return listOf(DatabaseHelper.TabRecord(
            "Переписка не загружена",
            "В облаке пока нет mail.db.gz.\n\nВ Windows-программе откройте вкладку «Переписка» и нажмите «Синхронизация», затем нажмите «Синхронизировать» здесь."))
        val out = mutableListOf<DatabaseHelper.TabRecord>()
        try {
            val where = if (project != null) "WHERE project_name=?" else ""
            val args = if (project != null) arrayOf(project) else emptyArray()

            db.rawQuery("SELECT COUNT(*) n, SUM(CASE WHEN status='Новое' THEN 1 ELSE 0 END) new, " +
                "SUM(CASE WHEN needs_reply=1 AND replied_at='' AND direction='Входящее' AND status!='Закрыто' THEN 1 ELSE 0 END) wait, " +
                "SUM(CASE WHEN risk_flag=1 THEN 1 ELSE 0 END) risk, " +
                "SUM(CASE WHEN order_batch_id>0 THEN 1 ELSE 0 END) linked FROM messages $where", args).use { c ->
                if (c.moveToFirst()) out.add(DatabaseHelper.TabRecord(
                    "📊 Сводка переписки",
                    "Писем: ${c.i("n")}\nНовых: ${c.i("new")}\nБез ответа: ${c.i("wait")}\n⚠ Риски: ${c.i("risk")}\nПривязано к заказам: ${c.i("linked")}",
                    if (c.i("wait") > 0 || c.i("risk") > 0) 0xFFFFF2CCL else 0L))
            }

            // Надёжность поставщиков (по домену отправителя)
            data class Agg(var n: Int = 0, var answered: Int = 0, var risk: Int = 0, var waiting: Int = 0, val hours: MutableList<Double> = mutableListOf())
            val byDomain = HashMap<String, Agg>()
            val threads = HashMap<String, MutableList<Pair<Long, String>>>()
            db.rawQuery("SELECT thread_id, project_id, sender_email, date_iso, direction, risk_flag, needs_reply, replied_at FROM messages $where", args).use { c ->
                while (c.moveToNext()) {
                    val key = "${c.i("project_id")}:${c.s("thread_id")}"
                    threads.getOrPut(key) { mutableListOf() }.add(pd(c.s("date_iso")) to c.s("direction"))
                    if (c.s("direction") == "Входящее") {
                        val em = c.s("sender_email")
                        val dom = if (em.contains("@")) em.substringAfterLast("@") else em.ifEmpty { "—" }
                        val a = byDomain.getOrPut(dom) { Agg() }
                        a.n++
                        if (c.i("risk_flag") == 1) a.risk++
                        if (c.i("needs_reply") == 1 && c.s("replied_at").isEmpty()) a.waiting++
                    }
                }
            }
            db.rawQuery("SELECT thread_id, project_id, sender_email, date_iso, direction FROM messages $where AND 1=1".replace("WHERE  AND", "WHERE").let { if (project != null) "SELECT thread_id, project_id, sender_email, date_iso, direction FROM messages WHERE project_name=? AND direction='Входящее'" else "SELECT thread_id, project_id, sender_email, date_iso, direction FROM messages WHERE direction='Входящее'" }, args).use { c ->
                while (c.moveToNext()) {
                    val d0 = pd(c.s("date_iso"))
                    if (d0 == 0L) continue
                    val key = "${c.i("project_id")}:${c.s("thread_id")}"
                    val reply = threads[key]?.filter { it.second == "Исходящее" && it.first > d0 }?.minByOrNull { it.first }
                    val em = c.s("sender_email")
                    val dom = if (em.contains("@")) em.substringAfterLast("@") else em.ifEmpty { "—" }
                    val a = byDomain.getOrPut(dom) { Agg() }
                    if (reply != null) { a.answered++; a.hours.add((reply.first - d0) / 3600000.0) }
                }
            }
            if (byDomain.isNotEmpty()) {
                val sb = StringBuilder("Надёжность поставщиков (по домену почты):")
                for ((dom, a) in byDomain.entries.sortedWith(compareByDescending { it.value.risk }).take(30)) {
                    val med = if (a.hours.isNotEmpty()) a.hours.sorted()[a.hours.size / 2] / 24.0 else null
                    sb.append("\n\n• $dom\n  писем ${a.n} · отвечено ${a.answered} · ждут ответа ${a.waiting} · ⚠ ${a.risk}")
                    if (med != null) sb.append("\n  ответ (медиана): ${"%.1f".format(med)} дн")
                }
                out.add(DatabaseHelper.TabRecord("📈 Надёжность поставщиков", sb.toString()))
            }

            // Письма (последнее в треде)
            val tw = if (project != null) "WHERE m.project_name=?" else ""
            db.rawQuery("SELECT m.*, (SELECT COUNT(*) FROM messages x WHERE x.project_id=m.project_id AND x.thread_id=m.thread_id) AS thread_n " +
                "FROM messages m $tw " +
                (if (project != null) "AND" else "WHERE") + " m.id=(SELECT x.id FROM messages x WHERE x.project_id=m.project_id AND x.thread_id=m.thread_id ORDER BY x.date_iso DESC, x.id DESC LIMIT 1) " +
                "ORDER BY m.date_iso DESC, m.id DESC LIMIT 300", args).use { c ->
                while (c.moveToNext()) {
                    val mid = c.i("id")
                    val wait = c.i("needs_reply") == 1 && c.s("replied_at").isEmpty() && c.s("direction") == "Входящее" && c.s("status") != "Закрыто"
                    val risk = c.i("risk_flag") == 1
                    val flags = (if (risk) "⚠" else "") + (if (wait) "✉" else "")
                    val color = when { risk -> 0xFFF4CCCCL; wait -> 0xFFFFF2CCL; else -> 0L }
                    val title = "$flags ${c.s("date_sent").ifEmpty { c.s("date_iso") }} · ${short(c.s("sender"), 20)} · ${short(c.s("subject"), 40)}"
                    val det = StringBuilder()
                    det.append("Проект: ${c.s("project_name")}\nДата: ${c.s("date_sent").ifEmpty { c.s("date_iso") }}\n")
                    det.append("От: ${c.s("sender")}\nКому: ${c.s("recipients")}\nТема: ${c.s("subject")}\n")
                    det.append("Направление: ${c.s("work_type").ifEmpty { "—" }}\nПоток: ${c.s("direction")}\nСтатус: ${c.s("status")}\n")
                    if (risk) det.append("⚠ Риски: ${c.s("risk_words")}\n")
                    if (wait) det.append("✉ Требует ответа\n")
                    if (c.i("order_batch_id") > 0) det.append("🔗 Заказ №${c.i("order_batch_id")}\n")
                    if (c.s("invoice_number").isNotEmpty()) det.append("Инвойс: ${c.s("invoice_number")}\n")
                    if (c.s("note").isNotEmpty()) det.append("Заметка: ${c.s("note")}\n")
                    db.rawQuery("SELECT kind, value, extra FROM extracted WHERE msg_id=? ORDER BY kind, id", arrayOf(mid.toString())).use { e ->
                        var has = false
                        while (e.moveToNext()) {
                            if (!has) { det.append("\nИзвлечено:"); has = true }
                            det.append("\n• ${e.s("kind")}: ${e.s("value")}${if (e.s("extra").isNotEmpty()) " (${e.s("extra")})" else ""}")
                        }
                    }
                    db.rawQuery("SELECT name, size FROM attachments WHERE msg_id=? ORDER BY id", arrayOf(mid.toString())).use { a ->
                        var has = false
                        while (a.moveToNext()) {
                            if (!has) { det.append("\n\nВложения:"); has = true }
                            det.append("\n📎 ${a.s("name")} (${a.i("size") / 1024} КБ)")
                        }
                    }
                    val tn = c.i("thread_n")
                    if (tn > 1) {
                        det.append("\n\nЦепочка ($tn):")
                        db.rawQuery("SELECT date_sent, date_iso, sender, subject, direction FROM messages WHERE project_id=? AND thread_id=? ORDER BY date_iso, id LIMIT 20",
                            arrayOf(c.s("project_id"), c.s("thread_id"))).use { t ->
                            while (t.moveToNext()) det.append("\n• ${t.s("date_sent").ifEmpty { t.s("date_iso") }} · ${short(t.s("sender"), 20)} · ${short(t.s("subject"), 40)}")
                        }
                    }
                    db.rawQuery("SELECT body FROM bodies WHERE msg_id=?", arrayOf(mid.toString())).use { b ->
                        if (b.moveToFirst()) {
                            val body = b.s("body")
                            if (body.isNotEmpty()) det.append("\n\nТекст письма:\n${short(body, 1500)}")
                        }
                    }
                    out.add(DatabaseHelper.TabRecord(title, det.toString(), color))
                }
            }
        } catch (e: Exception) {
            out.add(DatabaseHelper.TabRecord("Ошибка чтения переписки", e.message ?: ""))
        } finally { db.close() }
        val q = search.trim().lowercase()
        return if (q.isEmpty()) out else out.filter { (it.title + "\n" + it.details).lowercase().contains(q) }
    }

    fun workNames(context: Context): DatabaseHelper.TabRecord? {
        val db = DatabaseHelper(context)
        if (!db.isDatabaseReady()) return null
        return try {
            val sb = StringBuilder("База наименований работ:")
            var cnt = 0
            db.readableDatabase.rawQuery("SELECT name, work_type, duration_qty, duration_unit FROM work_names ORDER BY name", null).use { c ->
                while (c.moveToNext()) {
                    cnt++
                    sb.append("\n\n• ${c.s("name")}")
                    if (c.s("work_type").isNotEmpty()) sb.append(" · ${c.s("work_type")}")
                    val d = c.getColumnIndex("duration_qty")
                    if (d >= 0 && !c.isNull(d) && c.getDouble(d) > 0) sb.append(" · ${c.getDouble(d)} ${c.s("duration_unit")}")
                }
            }
            if (cnt > 0) DatabaseHelper.TabRecord("📚 База наименований работ ($cnt)", sb.toString()) else null
        } catch (e: Exception) { null }
    }
}
