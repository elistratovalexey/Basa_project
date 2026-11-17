package com.elistratov.basaproject

import android.content.Context
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ListView
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.TextView
import androidx.fragment.app.Fragment

class DataTabFragment : Fragment() {

    private lateinit var db: DatabaseHelper
    private lateinit var spinner: Spinner
    private lateinit var search: EditText
    private lateinit var listView: ListView
    private lateinit var listAdapter: ArrayAdapter<String>
    private lateinit var details: TextView
    private var records: List<DatabaseHelper.TabRecord> = emptyList()
    private var tab: String = ""
    private var suppressSpinner = false
    private val prefs by lazy { requireContext().getSharedPreferences("app_settings", Context.MODE_PRIVATE) }

    companion object {
        private const val ALL = "Все проекты"
        fun newInstance(tab: String) = DataTabFragment().apply {
            arguments = Bundle().apply { putString("tab", tab) }
        }
    }

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        tab = arguments?.getString("tab") ?: ""
        val ctx = requireContext()
        db = DatabaseHelper(ctx)
        val dp = { v: Int -> (resources.displayMetrics.density * v).toInt() }

        val root = LinearLayout(ctx).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), dp(8), dp(12), dp(8)) }
        spinner = Spinner(ctx)
        search = EditText(ctx).apply { hint = "Поиск по всем полям..."; setSingleLine() }

        listView = ListView(ctx).apply { choiceMode = ListView.CHOICE_MODE_SINGLE }
        listAdapter = ArrayAdapter(ctx, android.R.layout.simple_list_item_activated_1, mutableListOf<String>())
        listView.adapter = listAdapter

        details = TextView(ctx).apply { textSize = 14f; textIsSelectable = true; text = "Выберите запись в списке выше" }
        val scroll = ScrollView(ctx).apply { addView(details, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)); setPadding(0, dp(8), 0, 0) }

        root.addView(spinner, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(search, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply { topMargin = dp(4); bottomMargin = dp(4) })
        root.addView(listView, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        root.addView(View(ctx).apply { setBackgroundColor(0xFFCCCCCC.toInt()) }, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(1)))
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))

        listView.onItemClickListener = AdapterView.OnItemClickListener { _, _, position, _ ->
            listView.setItemChecked(position, true)
            details.text = records.getOrNull(position)?.details ?: ""
        }
        spinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                if (suppressSpinner) return
                prefs.edit().putString("selected_project", spinner.selectedItem?.toString() ?: ALL).apply()
                refresh()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }
        search.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {}
            override fun afterTextChanged(s: Editable?) { refresh() }
        })
        return root
    }

    override fun onResume() {
        super.onResume()
        val names = mutableListOf(ALL)
        names.addAll(db.getProjectNames())
        val saved = prefs.getString("selected_project", ALL)
        suppressSpinner = true
        spinner.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_item, names).also {
            it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        }
        spinner.setSelection(names.indexOf(saved).coerceAtLeast(0))
        suppressSpinner = false
        refresh()
    }

    private fun refresh() {
        val proj = spinner.selectedItem?.toString()?.takeIf { it != ALL }
        records = if (!db.isDatabaseReady())
            listOf(DatabaseHelper.TabRecord("База не загружена", "Нажмите ⚙️, настройте облако Mail.ru и нажмите «Синхронизировать» на главном экране."))
        else db.tabData(tab, proj, search.text.toString())
        listAdapter.clear()
        listAdapter.addAll(if (records.isEmpty()) listOf("Ничего не найдено") else records.map { it.title })
        listAdapter.notifyDataSetChanged()
        details.text = "Выберите запись в списке выше"
    }
}