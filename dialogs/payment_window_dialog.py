import tkinter as tk
from tkinter import ttk, messagebox

class PaymentWindowDialog(tk.Toplevel):
    def __init__(self, parent, spec_id, spec_data, db_manager):
        super().__init__(parent)
        self.title(f"Оплаты позиции №{spec_id}: {spec_data.get('name', '')}")
        self.geometry("900x600")
        self.db_manager = db_manager
        self.spec_id = spec_id
        self.spec_data = spec_data
        self.result_sum = 0
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Добавить платёж", command=self.add_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_payment).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Перенести сумму в спецификацию", command=self.transfer_sum).pack(side=tk.RIGHT, padx=5)
        
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cols = ("id", "number", "date", "amount", "currency", "percent", "paid",
                "invoice_number", "invoice_date", "supplier_name", "supplier_inn",
                "payment_purpose", "delivery_term", "delivery_date", "vat_amount", "total_with_vat")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15)
        headings = {"id": "ID", "number": "№", "date": "Дата", "amount": "Сумма", "currency": "Валюта",
            "percent": "%", "paid": "Оплачено", "invoice_number": "№ счёта", "invoice_date": "Дата счёта",
            "supplier_name": "Поставщик", "supplier_inn": "ИНН", "payment_purpose": "Назначение",
            "delivery_term": "Срок пост.", "delivery_date": "Дата пост.", "vat_amount": "НДС", "total_with_vat": "С НДС"}
        widths = {"id": 40, "number": 40, "date": 80, "amount": 90, "currency": 60, "percent": 50, "paid": 60,
            "invoice_number": 100, "invoice_date": 80, "supplier_name": 120, "supplier_inn": 100,
            "payment_purpose": 150, "delivery_term": 80, "delivery_date": 80, "vat_amount": 90, "total_with_vat": 100}
        for col in cols:
            self.tree.heading(col, text=headings.get(col, col))
            self.tree.column(col, width=widths.get(col, 80), anchor="center" if col in ("id","number","percent","paid") else "w")
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
        sum_frame = ttk.Frame(self)
        sum_frame.pack(fill=tk.X, padx=10, pady=5)
        self.lbl_total = ttk.Label(sum_frame, text="Итого: 0.00", font=("Arial", 12, "bold"), foreground="darkblue")
        self.lbl_total.pack(side=tk.LEFT, padx=10)
        
        self.load_payments()
        
        def _safe_grab():
            try:
                if self.winfo_exists() and self.winfo_viewable():
                    self.grab_set()
                else:
                    self.after(100, _safe_grab)
            except tk.TclError:
                self.after(100, _safe_grab)
        self.after(50, _safe_grab)

    def load_payments(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        total = 0
        for p in self.db_manager.get_purchase_payments_ext(self.spec_id):
            paid_mark = "✓" if p.get("paid") else ""
            self.tree.insert("", tk.END, values=(
                p["id"], p["number"] or "", p["date"] or "", f"{p['amount']:.2f}" if p.get("amount") else "0.00",
                p["currency"] or "", f"{p['percent']:.1f}" if p.get("percent") else "0.0", paid_mark,
                p.get("invoice_number", ""), p.get("invoice_date", ""), p.get("supplier_name", ""),
                p.get("supplier_inn", ""), p.get("payment_purpose", ""), p.get("delivery_term", ""),
                p.get("delivery_date", ""), f"{p['vat_amount']:.2f}" if p.get("vat_amount") else "0.00",
                f"{p['total_with_vat']:.2f}" if p.get("total_with_vat") else "0.00"))
            try: total += float(p.get("amount", 0) or 0)
            except: pass
        self.result_sum = total
        self.lbl_total.config(text=f"Итого: {total:,.2f} {self.spec_data.get('currency', '')}")

    def add_payment(self):
        dialog = PaymentEditDialog(self, None, self.db_manager, self.spec_data)
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.add_purchase_payment_ext(self.spec_id, dialog.result)
            self.load_payments()

    def edit_payment(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платёж!")
            return
        v = self.tree.item(selected[0])['values']
        data = {'id': v[0], 'number': v[1], 'date': v[2], 'amount': float(v[3]) if v[3] else 0, 'currency': v[4],
            'percent': float(v[5]) if v[5] else 0, 'paid': 1 if v[6] == "✓" else 0, 'invoice_number': v[7],
            'invoice_date': v[8], 'supplier_name': v[9], 'supplier_inn': v[10], 'payment_purpose': v[11],
            'delivery_term': v[12], 'delivery_date': v[13], 'vat_amount': float(v[14]) if v[14] else 0,
            'total_with_vat': float(v[15]) if v[15] else 0}
        dialog = PaymentEditDialog(self, data, self.db_manager, self.spec_data)
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.update_purchase_payment_ext(data['id'], dialog.result)
            self.load_payments()

    def delete_payment(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите платёж!")
            return
        if messagebox.askyesno("Подтверждение", "Удалить платёж?"):
            self.db_manager.conn.execute("DELETE FROM purchase_payments WHERE id=?", (self.tree.item(selected[0])['values'][0],))
            self.db_manager.conn.commit()
            self.load_payments()

    def transfer_sum(self):
        self.result_sum_value = self.result_sum
        self.destroy()


class PaymentEditDialog(tk.Toplevel):
    def __init__(self, parent, data, db_manager, spec_data):
        super().__init__(parent)
        self.title("Редактировать платёж")
        self.geometry("700x500")
        self.db_manager = db_manager
        self.spec_data = spec_data
        self.result = None
        
        fields = [("№", "number", 10), ("Дата", "date", 15), ("Сумма", "amount", 15), ("Валюта", "currency", 10),
            ("%", "percent", 10), ("№ счёта", "invoice_number", 15), ("Дата счёта", "invoice_date", 15),
            ("Поставщик", "supplier_name", 30), ("ИНН поставщика", "supplier_inn", 15),
            ("Срок поставки", "delivery_term", 15), ("Дата поставки", "delivery_date", 15),
            ("НДС", "vat_amount", 15), ("Сумма с НДС", "total_with_vat", 15)]
        self.entries = {}
        for i, (label, key, width) in enumerate(fields):
            ttk.Label(self, text=label + ":").grid(row=i, column=0, sticky="w", padx=10, pady=3)
            entry = ttk.Entry(self, width=width)
            entry.grid(row=i, column=1, sticky="ew", padx=10, pady=3)
            self.entries[key] = entry
            
        ttk.Label(self, text="Назначение платежа:").grid(row=len(fields), column=0, sticky="nw", padx=10, pady=3)
        self.entry_purpose = tk.Text(self, width=40, height=3)
        self.entry_purpose.grid(row=len(fields), column=1, sticky="ew", padx=10, pady=3)
        self.paid_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Оплачено", variable=self.paid_var).grid(row=len(fields)+1, column=0, columnspan=2, padx=10, pady=5)
        self.grid_columnconfigure(1, weight=1)
        
        if data:
            for key, entry in self.entries.items():
                entry.insert(0, str(data.get(key, '')) if data.get(key) else '')
            self.entry_purpose.insert("1.0", data.get('payment_purpose', ''))
            self.paid_var.set(bool(data.get('paid', 0)))
            
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=len(fields)+2, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        def _safe_grab():
            try:
                if self.winfo_exists() and self.winfo_viewable():
                    self.grab_set()
                else:
                    self.after(100, _safe_grab)
            except tk.TclError:
                self.after(100, _safe_grab)
        self.after(50, _safe_grab)

    def save(self):
        try:
            amount = float(self.entries['amount'].get() or 0)
            percent = float(self.entries['percent'].get() or 0)
            vat = float(self.entries['vat_amount'].get() or 0)
            total_vat = float(self.entries['total_with_vat'].get() or 0)
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное число!")
            return
        self.result = {
            'number': int(self.entries['number'].get() or 1), 'date': self.entries['date'].get(),
            'amount': amount, 'currency': self.entries['currency'].get() or self.spec_data.get('currency', 'RUB'),
            'percent': percent, 'paid': 1 if self.paid_var.get() else 0,
            'invoice_number': self.entries['invoice_number'].get(), 'invoice_date': self.entries['invoice_date'].get(),
            'supplier_name': self.entries['supplier_name'].get(), 'supplier_inn': self.entries['supplier_inn'].get(),
            'payment_purpose': self.entry_purpose.get("1.0", tk.END).strip(),
            'delivery_term': self.entries['delivery_term'].get(), 'delivery_date': self.entries['delivery_date'].get(),
            'vat_amount': vat, 'total_with_vat': total_vat,
        }
        self.destroy()