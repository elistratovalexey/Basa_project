# -*- coding: utf-8 -*-
"""Окно оплат по спецификации закупок.

Ключевое: введённая сумма платежа = факт оплаты. Флаг «Оплачен» ставится
автоматически, иначе бюджет и дашборд не видят реальные оплаты.
"""
import tkinter as tk
from tkinter import ttk, messagebox


def _num(x, default=0.0):
    try:
        return float(str(x).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


class PaymentWindowDialog(tk.Toplevel):
    """Список оплат счёта + итог по суммам."""

    def __init__(self, parent, spec_id, spec_data, db_manager):
        super().__init__(parent)
        self.db_manager = db_manager
        self.spec_id = spec_id
        self.spec_data = dict(spec_data) if spec_data else {}
        self.result_sum = 0.0
        self.result_sum_value = None

        self.title(f"Оплаты по спецификации #{spec_id}")
        self.geometry("1000x620")
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "payment_window", "1000x620")
            track_geometry(self, "payment_window")
        except Exception:
            pass
        self.transient(parent)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self.add_payment).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_payment).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_payment).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Отметить все оплаченными",
                   command=self.mark_all_paid).pack(side=tk.LEFT, padx=12)
        ttk.Button(btn_frame, text="Перенести сумму в спецификацию",
                   command=self.transfer_sum).pack(side=tk.RIGHT, padx=4)

        tree_frame = ttk.LabelFrame(self, text="Список оплат", padding=6)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols = ("id", "number", "date", "amount", "currency", "percent", "paid",
                "invoice_number", "invoice_date", "supplier_name", "supplier_inn",
                "payment_purpose", "delivery_term", "delivery_date", "vat_amount", "total_with_vat")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=12)
        headings = {
            "id": "ID", "number": "№ платежа", "date": "Дата", "amount": "Сумма",
            "currency": "Валюта", "percent": "% от суммы", "paid": "Оплачен",
            "invoice_number": "№ счёта", "invoice_date": "Дата счёта",
            "supplier_name": "Поставщик", "supplier_inn": "ИНН",
            "payment_purpose": "Назначение", "delivery_term": "Срок пост.",
            "delivery_date": "Дата пост.", "vat_amount": "НДС", "total_with_vat": "С НДС",
        }
        widths = {
            "id": 45, "number": 75, "date": 85, "amount": 100, "currency": 65,
            "percent": 80, "paid": 70, "invoice_number": 100, "invoice_date": 85,
            "supplier_name": 140, "supplier_inn": 100, "payment_purpose": 160,
            "delivery_term": 85, "delivery_date": 85, "vat_amount": 90, "total_with_vat": 100,
        }
        for col in cols:
            self.tree.heading(col, text=headings.get(col, col))
            self.tree.column(col, width=widths.get(col, 90),
                             anchor="center" if col in ("id", "number", "percent", "paid")
                             else ("e" if col in ("amount", "vat_amount", "total_with_vat") else "w"))
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hs = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=sb.set, xscroll=hs.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        hs.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.tag_configure("unpaid", background="#fff2cc")
        self.tree.bind("<Double-1>", lambda e: self.edit_payment())

        sum_frame = ttk.Frame(self)
        sum_frame.pack(fill=tk.X, padx=10, pady=6)
        self.lbl_total = ttk.Label(sum_frame, text="", font=("Arial", 10, "bold"),
                                   foreground="darkblue")
        self.lbl_total.pack(side=tk.LEFT, padx=4)

        bf = ttk.Frame(self)
        bf.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(bf, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=4)

        self.load_payments()
        self.bind("<Escape>", lambda e: self.destroy())
        self._safe_grab()

    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))

    # ---------------- сумма счёта ----------------
    def spec_total(self):
        """Сумма счёта: total → кол-во × цена → сумма позиций."""
        t = _num(self.spec_data.get("total"))
        if t > 0:
            return t
        t = _num(self.spec_data.get("quantity")) * _num(self.spec_data.get("price"))
        if t > 0:
            return t
        try:
            items = self.db_manager.get_purchase_spec_items(self.spec_id)
            return sum(_num(i["total"]) or _num(i["quantity"]) * _num(i["price"]) for i in items)
        except Exception:
            return 0.0

    def _sync_spec_paid(self, paid_sum, total):
        """Обновляет fully_paid у счёта, чтобы дашборд не считал его долгом."""
        try:
            need = 1 if (total > 0 and paid_sum >= total - 0.01) else 0
            self.db_manager.conn.execute(
                "UPDATE purchase_specifications SET fully_paid=? WHERE id=?", (need, self.spec_id))
            self.db_manager.conn.commit()
        except Exception as e:
            print(f"[payments] fully_paid: {e}")

    # ---------------- загрузка ----------------
    def load_payments(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        total_sum = 0.0
        paid_sum = 0.0
        try:
            rows = self.db_manager.get_purchase_payments_ext(self.spec_id)
        except Exception:
            rows = self.db_manager.get_purchase_payments(self.spec_id)
        for p in rows:
            amount = _num(p["amount"])
            paid = bool(p["paid"])
            total_sum += amount
            if paid:
                paid_sum += amount
            keys = p.keys() if hasattr(p, "keys") else []

            def g(k, default=""):
                return (p[k] if k in keys else default) or default

            iid = self.tree.insert("", tk.END, values=(
                p["id"], p["number"] or "", p["date"] or "",
                f"{amount:,.2f}".replace(",", " "),
                p["currency"] or "", f"{_num(p['percent']):.1f}",
                "✓" if paid else "",
                g("invoice_number"), g("invoice_date"),
                g("supplier_name"), g("supplier_inn"),
                g("payment_purpose"), g("delivery_term"), g("delivery_date"),
                f"{_num(g('vat_amount', 0)):,.2f}".replace(",", " "),
                f"{_num(g('total_with_vat', 0)):,.2f}".replace(",", " "),
            ))
            if amount > 0 and not paid:
                self.tree.item(iid, tags=("unpaid",))

        self.result_sum = total_sum
        spec_total = self.spec_total()
        cur = self.spec_data.get("currency", "") or ""
        rest = spec_total - total_sum
        pct = (total_sum / spec_total * 100) if spec_total > 0 else 0.0
        if spec_total > 0 and total_sum >= spec_total - 0.01:
            state = "Оплачено полностью ✓"
            color = "#198754"
        elif total_sum > 0:
            state = f"Остаток: {rest:,.2f}".replace(",", " ")
            color = "#b02a37"
        else:
            state = "Не оплачено"
            color = "#b02a37"
        self.lbl_total.config(
            foreground=color,
            text=(f"Общая сумма: {spec_total:,.2f} {cur}   "
                  f"Оплачено: {total_sum:,.2f}   {state}   {pct:.1f}%").replace(",", " "))
        self._sync_spec_paid(total_sum, spec_total)

    # ---------------- CRUD ----------------
    def _next_number(self):
        nums = [int(_num(self.tree.item(i)["values"][1], 0)) for i in self.tree.get_children()]
        return (max(nums) if nums else 0) + 1

    def add_payment(self):
        prefill = {"number": self._next_number(),
                   "currency": self.spec_data.get("currency", "RUB"),
                   "supplier_name": self.spec_data.get("supplier", ""),
                   "amount": max(0.0, self.spec_total() - self.result_sum)}
        dialog = PaymentEditDialog(self, prefill, self.db_manager, self.spec_data,
                                   spec_total=self.spec_total())
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.add_purchase_payment_ext(self.spec_id, dialog.result)
            self.load_payments()

    def edit_payment(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платёж!", parent=self)
            return
        v = self.tree.item(selected[0])['values']
        data = {
            'id': v[0], 'number': v[1], 'date': v[2],
            'amount': _num(v[3]), 'currency': v[4], 'percent': _num(v[5]),
            'paid': 1 if v[6] == "✓" else 0,
            'invoice_number': v[7], 'invoice_date': v[8],
            'supplier_name': v[9], 'supplier_inn': v[10],
            'payment_purpose': v[11], 'delivery_term': v[12], 'delivery_date': v[13],
            'vat_amount': _num(v[14]), 'total_with_vat': _num(v[15]),
        }
        dialog = PaymentEditDialog(self, data, self.db_manager, self.spec_data,
                                   spec_total=self.spec_total())
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.update_purchase_payment_ext(data['id'], dialog.result)
            self.load_payments()

    def delete_payment(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платёж!", parent=self)
            return
        payment_id = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Подтверждение", "Удалить платёж?", parent=self):
            self.db_manager.delete_purchase_payment(payment_id)
            self.load_payments()

    def mark_all_paid(self):
        """Разово проставляет «Оплачен» всем платежам с суммой > 0."""
        marked = 0
        try:
            for p in self.db_manager.get_purchase_payments_ext(self.spec_id):
                if _num(p["amount"]) > 0 and not p["paid"]:
                    self.db_manager.conn.execute(
                        "UPDATE purchase_payments SET paid=1 WHERE id=?", (p["id"],))
                    marked += 1
            self.db_manager.conn.commit()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e), parent=self)
            return
        self.load_payments()
        messagebox.showinfo("Готово", f"Отмечено платежей: {marked}", parent=self)

    def transfer_sum(self):
        self.result_sum_value = self.result_sum
        self.destroy()


class PaymentEditDialog(tk.Toplevel):
    """Карточка платежа. Сумма > 0 ⇒ «Оплачен» ставится автоматически."""

    def __init__(self, parent, data, db_manager, spec_data, spec_total=0.0):
        super().__init__(parent)
        self.db_manager = db_manager
        self.spec_data = spec_data or {}
        self.spec_total = spec_total
        self.result = None

        self.title("Редактировать платёж" if (data or {}).get("id") else "Новый платёж")
        self.geometry("700x560")
        self.resizable(False, False)
        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "payment_edit", "700x560")
            track_geometry(self, "payment_edit")
        except Exception:
            pass
        self.transient(parent)

        fields = [
            ("№", "number", 10), ("Дата", "date", 15), ("Сумма", "amount", 15),
            ("Валюта", "currency", 10), ("%", "percent", 10),
            ("№ счёта", "invoice_number", 15), ("Дата счёта", "invoice_date", 15),
            ("Поставщик", "supplier_name", 30), ("ИНН поставщика", "supplier_inn", 15),
            ("Срок поставки", "delivery_term", 15), ("Дата поставки", "delivery_date", 15),
            ("НДС", "vat_amount", 15), ("Сумма с НДС", "total_with_vat", 15),
        ]
        self.entries = {}
        for i, (label, key, width) in enumerate(fields):
            ttk.Label(self, text=label + ":").grid(row=i, column=0, sticky="w", padx=10, pady=3)
            entry = ttk.Entry(self, width=width)
            entry.grid(row=i, column=1, sticky="ew", padx=10, pady=3)
            self.entries[key] = entry

        ttk.Label(self, text="Назначение платежа:").grid(row=len(fields), column=0,
                                                         sticky="nw", padx=10, pady=3)
        self.entry_purpose = tk.Text(self, width=40, height=3)
        self.entry_purpose.grid(row=len(fields), column=1, sticky="ew", padx=10, pady=3)

        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Оплачен (ставится автоматически при сумме > 0)",
                        variable=self.paid_var).grid(row=len(fields) + 1, column=0,
                                                     columnspan=2, sticky="w", padx=10, pady=5)
        self.lbl_hint = ttk.Label(self, text="", foreground="gray")
        self.lbl_hint.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", padx=10)
        self.grid_columnconfigure(1, weight=1)

        if data:
            for key, entry in self.entries.items():
                val = data.get(key, '')
                entry.insert(0, str(val) if val not in (None, "") else '')
            self.entry_purpose.insert("1.0", data.get('payment_purpose', '') or "")
            self.paid_var.set(bool(data.get('paid', 0)))

        # сумма ↔ проценты
        self.entries["amount"].bind("<KeyRelease>", lambda e: self._recalc_from_amount())
        self.entries["percent"].bind("<KeyRelease>", lambda e: self._recalc_from_percent())
        self._recalc_from_amount()

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=len(fields) + 3, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)

        self.bind("<Escape>", lambda e: self.destroy())
        self._safe_grab()

    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(60, lambda a=attempts - 1: self._safe_grab(a))

    def _recalc_from_amount(self):
        if self.spec_total <= 0:
            self.lbl_hint.config(text="Сумма счёта не задана — % не рассчитывается")
            return
        amount = _num(self.entries["amount"].get())
        pct = amount / self.spec_total * 100
        self.lbl_hint.config(text=f"Сумма счёта {self.spec_total:,.2f} · это {pct:.1f}%".replace(",", " "))
        if amount > 0:
            self.paid_var.set(True)
            e = self.entries["percent"]
            if not e.get().strip():
                e.insert(0, f"{pct:.1f}")

    def _recalc_from_percent(self):
        if self.spec_total <= 0:
            return
        pct = _num(self.entries["percent"].get())
        if pct > 0 and not self.entries["amount"].get().strip():
            self.entries["amount"].insert(0, f"{self.spec_total * pct / 100:.2f}")
            self.paid_var.set(True)

    def save(self):
        def num(key):
            return _num(self.entries[key].get())

        try:
            number = int(_num(self.entries['number'].get(), 1)) or 1
        except (TypeError, ValueError):
            number = 1

        amount = num('amount')
        percent = num('percent')
        # сумма ↔ проценты: заполняем недостающее
        if self.spec_total > 0:
            if amount > 0 and percent <= 0:
                percent = round(amount / self.spec_total * 100, 2)
            elif percent > 0 and amount <= 0:
                amount = round(self.spec_total * percent / 100, 2)

        # ГЛАВНОЕ: введённая сумма = факт оплаты
        paid = 1 if (amount > 0 or self.paid_var.get()) else 0

        self.result = {
            'number': number,
            'date': self.entries['date'].get().strip(),
            'amount': amount,
            'currency': self.entries['currency'].get().strip() or self.spec_data.get('currency', 'RUB'),
            'percent': percent,
            'paid': paid,
            'invoice_number': self.entries['invoice_number'].get().strip(),
            'invoice_date': self.entries['invoice_date'].get().strip(),
            'supplier_name': self.entries['supplier_name'].get().strip() or self.spec_data.get('supplier', ''),
            'supplier_inn': self.entries['supplier_inn'].get().strip(),
            'payment_purpose': self.entry_purpose.get("1.0", tk.END).strip(),
            'delivery_term': self.entries['delivery_term'].get().strip(),
            'delivery_date': self.entries['delivery_date'].get().strip(),
            'vat_amount': num('vat_amount'),
            'total_with_vat': num('total_with_vat'),
        }
        self.destroy()