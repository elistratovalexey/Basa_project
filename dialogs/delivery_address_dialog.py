import tkinter as tk
from tkinter import ttk, messagebox


class DeliveryAddressDialog(tk.Toplevel):
    def __init__(self, parent, db_manager):
        super().__init__(parent)
        self.title("База адресов доставки")
        self.geometry("700x500")
        self.db_manager = db_manager
        
        # Кнопки управления
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(btn_frame, text="Добавить", command=self.add_address).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Редактировать", command=self.edit_address).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Удалить", command=self.delete_address).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        
        # Таблица
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        cols = ("id", "name", "address", "contact", "phone", "note")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15)
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Название")
        self.tree.heading("address", text="Адрес")
        self.tree.heading("contact", text="Контакт")
        self.tree.heading("phone", text="Телефон")
        self.tree.heading("note", text="Примечание")
        
        self.tree.column("id", width=40, anchor="center")
        self.tree.column("name", width=120, anchor="w")
        self.tree.column("address", width=250, anchor="w")
        self.tree.column("contact", width=120, anchor="w")
        self.tree.column("phone", width=100, anchor="w")
        self.tree.column("note", width=150, anchor="w")
        
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.load_addresses()
        self.grab_set()
    
    def load_addresses(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for addr in self.db_manager.get_delivery_addresses():
            self.tree.insert("", tk.END, values=(
                addr['id'], addr['name'] or '', addr['address'] or '',
                addr['contact'] or '', addr['phone'] or '', addr['note'] or ''
            ))
    
    def add_address(self):
        dialog = AddressEditDialog(self, None, self.db_manager)
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.add_delivery_address(dialog.result)
            self.load_addresses()
    
    def edit_address(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите адрес!")
            return
        v = self.tree.item(selected[0])['values']
        data = {
            'id': v[0], 'name': v[1], 'address': v[2],
            'contact': v[3], 'phone': v[4], 'note': v[5]
        }
        dialog = AddressEditDialog(self, data, self.db_manager)
        self.wait_window(dialog)
        if dialog.result:
            self.db_manager.update_delivery_address(data['id'], dialog.result)
            self.load_addresses()
    
    def delete_address(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите адрес!")
            return
        addr_id = self.tree.item(selected[0])['values'][0]
        if messagebox.askyesno("Подтверждение", "Удалить адрес?"):
            self.db_manager.delete_delivery_address(addr_id)
            self.load_addresses()


class AddressEditDialog(tk.Toplevel):
    def __init__(self, parent, data, db_manager):
        super().__init__(parent)
        self.title("Редактировать адрес доставки")
        self.geometry("500x350")
        self.db_manager = db_manager
        self.result = None
        
        ttk.Label(self, text="Название:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_name = ttk.Entry(self, width=40)
        self.entry_name.grid(row=0, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="Адрес:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.entry_address = ttk.Entry(self, width=40)
        self.entry_address.grid(row=1, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="Контакт:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_contact = ttk.Entry(self, width=40)
        self.entry_contact.grid(row=2, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="Телефон:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_phone = ttk.Entry(self, width=40)
        self.entry_phone.grid(row=3, column=1, sticky="ew", padx=10, pady=5)
        
        ttk.Label(self, text="Примечание:").grid(row=4, column=0, sticky="w", padx=10, pady=5)
        self.entry_note = ttk.Entry(self, width=40)
        self.entry_note.grid(row=4, column=1, sticky="ew", padx=10, pady=5)
        
        self.grid_columnconfigure(1, weight=1)
        
        if data:
            self.entry_name.insert(0, data.get('name', ''))
            self.entry_address.insert(0, data.get('address', ''))
            self.entry_contact.insert(0, data.get('contact', ''))
            self.entry_phone.insert(0, data.get('phone', ''))
            self.entry_note.insert(0, data.get('note', ''))
        
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        
        self.grab_set()
    
    def save(self):
        self.result = {
            'name': self.entry_name.get(),
            'address': self.entry_address.get(),
            'contact': self.entry_contact.get(),
            'phone': self.entry_phone.get(),
            'note': self.entry_note.get(),
        }
        self.destroy()