import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import time
import json
import os

try:
    from config import CURRENCIES
except ImportError:
    CURRENCIES = ["RUB", "USD", "EUR", "CNY", "TRY"]

try:
    from deep_translator import GoogleTranslator, MyMemoryTranslator
    from deep_translator.exceptions import TooManyRequests
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    GoogleTranslator = None
    MyMemoryTranslator = None

    class TooManyRequests(Exception):
        """Заглушка, если deep_translator не установлена"""
        pass

# === КЭШ ПЕРЕВОДОВ ===
CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "translation_cache.json")


def load_translation_cache():
    """Загрузить кэш переводов"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_translation_cache(cache):
    """Сохранить кэш переводов"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения кэша: {e}")


# === ЛОКАЛЬНЫЙ СЛОВАРЬ ТЕХНИЧЕСКИХ ТЕРМИНОВ ===
TECH_DICT = {
    'каретка': 'carriage', 'рельс': 'rail', 'рельсовая направляющая': 'linear guide rail',
    'направляющая': 'guide', 'линейный': 'linear', 'подшипник': 'bearing', 'вал': 'shaft',
    'цилиндр': 'cylinder', 'пневмоцилиндр': 'pneumatic cylinder', 'дроссель': 'throttle',
    'штуцер': 'fitting', 'датчик': 'sensor', 'муфта': 'coupling', 'фланец': 'flange',
    'опора': 'support', 'стойка': 'column', 'кронштейн': 'bracket', 'зажим': 'clamp',
    'прижим': 'clamp', 'механизм': 'mechanism', 'привод': 'drive', 'двигатель': 'motor',
    'насос': 'pump', 'клапан': 'valve', 'фильтр': 'filter', 'регулятор': 'regulator',
    'манометр': 'pressure gauge', 'трубка': 'tube', 'шланг': 'hose', 'кабель': 'cable',
    'разъем': 'connector', 'контроллер': 'controller', 'реле': 'relay', 'контактор': 'contactor',
    'автомат': 'circuit breaker', 'предохранитель': 'fuse', 'трансформатор': 'transformer',
    'источник питания': 'power supply', 'блок питания': 'power supply unit', 'аккумулятор': 'battery',
    'зарядное устройство': 'charger', 'инвертор': 'inverter', 'преобразователь': 'converter',
    'усилитель': 'amplifier', 'энкодер': 'encoder', 'редуктор': 'gearbox', 'ремень': 'belt',
    'цепь': 'chain', 'звездочка': 'sprocket', 'шкив': 'pulley', 'винт': 'screw', 'болт': 'bolt',
    'гайка': 'nut', 'шайба': 'washer', 'пружина': 'spring', 'уплотнение': 'seal',
    'прокладка': 'gasket', 'кольцо': 'ring', 'втулка': 'bushing', 'шпонка': 'key', 'штифт': 'pin',
    'ось': 'axis', 'поперечный': 'cross', 'продольный': 'longitudinal', 'вертикальный': 'vertical',
    'горизонтальный': 'horizontal', 'одиночный': 'single', 'двойной': 'double', 'тройной': 'triple',
    'пушер': 'pusher', 'позиционер': 'positioner', 'манипулятор': 'manipulator', 'захват': 'gripper',
    'конвейер': 'conveyor', 'стол': 'table', 'платформа': 'platform', 'рама': 'frame',
    'корпус': 'housing', 'крышка': 'cover', 'дверца': 'door', 'панель': 'panel', 'экран': 'screen',
    'дисплей': 'display', 'индикатор': 'indicator', 'сигнальная лампа': 'signal lamp',
    'кнопка': 'button', 'переключатель': 'switch', 'тумблер': 'toggle switch', 'зеркальный': 'mirror',
    'исполнение': 'version', 'мотор': 'motor', 'входной': 'input', 'выходной': 'output',
    'роликовый': 'roller', 'роликовый конвейер': 'roller conveyor', 'приводной': 'driven',
    'лабиринтное уплотнение': 'labyrinth seal', 'лабиринт': 'labyrinth', 'однорядный': 'single-row',
    'входной конвейер': 'input conveyor', 'шкаф': 'cabinet', 'шкафы': 'cabinets', 'замок': 'lock',
    'замки': 'locks', 'дверь': 'door', 'двери': 'doors', 'для дверей': 'for doors',
    'ролик': 'roller', 'ролики': 'rollers', 'зажимная втулка': 'clamping bushing',
    'колесо': 'wheel', 'колеса': 'wheels', 'колёса': 'wheels', 'поворотный': 'swivel',
    'поворотное': 'swivel', 'поворотная': 'swivel', 'полиуретан': 'polyurethane',
    'полиуретановый': 'polyurethane', 'полиуретановое': 'polyurethane', 'нейлон': 'nylon',
    'нейлоновый': 'nylon', 'резина': 'rubber', 'резиновый': 'rubber', 'рычаг': 'lever',
    'рукоятка': 'handle', 'ручка': 'handle', 'петля': 'hinge', 'шарнир': 'hinge',
    'шарнирный': 'hinged', 'головка': 'head', 'штекер': 'plug', 'ниппель': 'nipple',
    'тройник': 'tee', 'переходник': 'adapter', 'адаптер': 'adapter', 'удлинитель': 'extension',
    'крепеж': 'fastener', 'крепежный': 'fastening', 'резьба': 'thread', 'резьбовой': 'threaded',
    'метрический': 'metric', 'дюймовый': 'inch', 'фланцевый': 'flanged', 'торцевой': 'end',
    'боковой': 'side', 'верхний': 'upper', 'нижний': 'lower', 'внутренний': 'internal',
    'наружный': 'external', 'комплект': 'kit', 'набор': 'set', 'запасной': 'spare',
    'ремкомплект': 'repair kit', 'упор': 'stop', 'пружинный': 'spring-loaded',
    'буфер': 'buffer', 'демпфер': 'damper', 'ограничитель': 'limiter', 'фиксатор': 'lock',
    'защелка': 'latch', 'магнит': 'magnet', 'магнитный': 'magnetic', 'пластина': 'plate',
    'плита': 'plate', 'основание': 'base', 'профиль': 'profile', 'алюминий': 'aluminum',
    'алюминиевый': 'aluminum', 'сталь': 'steel', 'стальной': 'steel',
    'нержавеющий': 'stainless', 'латунь': 'brass', 'пластик': 'plastic', 'пластиковый': 'plastic',
}


class PurchaseDialog(tk.Toplevel):
    def __init__(self, parent, title, number, purchase_data=None,
                 db_manager=None, project_name=None):
        super().__init__(parent)
        self.title(title)
        self.geometry("1100x420")
        self.resizable(False, False)

        try:
            from dialogs.window_geometry import restore_geometry, track_geometry
            restore_geometry(self, "purchase_dialog", "1100x420")
            track_geometry(self, "purchase_dialog")
        except Exception:
            pass

        self.result = None
        self.db_manager = db_manager
        self.project_name = project_name or ""
        self.translation_cache = load_translation_cache()

        # Строка 0: №, Производитель, Подпроект
        ttk.Label(self, text="№:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.entry_number = ttk.Entry(self, width=12)
        self.entry_number.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        self.entry_number.insert(0, str(number))

        ttk.Label(self, text="Производитель:").grid(row=0, column=2, sticky="w", padx=10, pady=5)
        self.combo_manufacturer = ttk.Combobox(self, width=25)
        self.combo_manufacturer.grid(row=0, column=3, sticky="ew", padx=5, pady=5)
        self.load_manufacturers()

        ttk.Label(self, text="Подпроект:").grid(row=0, column=4, sticky="w", padx=10, pady=5)
        self.combo_subproject = ttk.Combobox(self, width=25)
        self.combo_subproject.grid(row=0, column=5, sticky="ew", padx=5, pady=5)
        self.load_subprojects()

        # Строка 1: КД, Артикул, Наименование (рус)
        ttk.Label(self, text="КД:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.combo_kd = ttk.Combobox(self, width=12)
        self.combo_kd.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.load_kd()

        ttk.Label(self, text="Артикул:").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.entry_article = ttk.Entry(self, width=25)
        self.entry_article.grid(row=1, column=3, sticky="ew", padx=5, pady=5)
        self.entry_article.bind('<KeyRelease>', lambda e: self.on_article_change())
        # НОВОЕ: подсказка истории цен при уходе из поля артикула
        self.entry_article.bind('<FocusOut>', lambda e: self.update_price_hint(), add="+")

        ttk.Label(self, text="Наименование (рус):").grid(row=1, column=4, sticky="w", padx=10, pady=5)
        self.entry_name = ttk.Entry(self, width=40)
        self.entry_name.grid(row=1, column=5, sticky="ew", padx=5, pady=5)
        self.entry_name.bind('<KeyRelease>', lambda e: self.on_name_change())

        # Строка 2: Наименование (анг) + кнопка перевода, Количество
        ttk.Label(self, text="Наименование (анг):").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.entry_name_eng = ttk.Entry(self, width=40)
        self.entry_name_eng.grid(row=2, column=1, sticky="ew", padx=5, pady=5, columnspan=3)

        self.btn_translate = ttk.Button(self, text=" Перевести", command=self.translate_name)
        self.btn_translate.grid(row=2, column=4, sticky="w", padx=5, pady=5)

        ttk.Label(self, text="Количество:").grid(row=2, column=5, sticky="w", padx=10, pady=5)
        self.entry_quantity = ttk.Entry(self, width=15)
        self.entry_quantity.grid(row=2, column=6, sticky="ew", padx=5, pady=5)

        # Строка 3: Примечание
        ttk.Label(self, text="Примечание:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.entry_note = ttk.Entry(self, width=70)
        self.entry_note.grid(row=3, column=1, columnspan=6, sticky="ew", padx=5, pady=5)

        # Строка 4: Заказано, Дата заказа, В заказ
        self.ordered_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Заказано", variable=self.ordered_var).grid(
            row=4, column=0, sticky="w", padx=10, pady=5)
        ttk.Label(self, text="Дата заказа:").grid(row=4, column=1, sticky="w", padx=10, pady=5)
        self.entry_order_date = ttk.Entry(self, width=18)
        self.entry_order_date.grid(row=4, column=2, sticky="w", padx=5, pady=5)
        self.btn_cal_order = ttk.Button(self, text="📅", width=3, command=self.select_order_date)
        self.btn_cal_order.grid(row=4, column=3, padx=5, pady=5)

        self.in_order_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="В заказ", variable=self.in_order_var).grid(
            row=4, column=4, sticky="w", padx=10, pady=5)

        # Строка 5: Получено, Дата получения, Запрос цены
        self.received_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Получено", variable=self.received_var).grid(
            row=5, column=0, sticky="w", padx=10, pady=5)
        ttk.Label(self, text="Дата получения:").grid(row=5, column=1, sticky="w", padx=10, pady=5)
        self.entry_receipt_date = ttk.Entry(self, width=18)
        self.entry_receipt_date.grid(row=5, column=2, sticky="w", padx=5, pady=5)
        self.btn_cal_receipt = ttk.Button(self, text="📅", width=3, command=self.select_receipt_date)
        self.btn_cal_receipt.grid(row=5, column=3, padx=5, pady=5)

        self.price_request_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text="Запрос цены", variable=self.price_request_var).grid(
            row=5, column=4, sticky="w", padx=10, pady=5)

        for col in (1, 3, 5):
            self.grid_columnconfigure(col, weight=1)

        # Заполняем данные если есть
        if purchase_data:
            self.combo_manufacturer.set(purchase_data.get("manufacturer", ""))
            self.combo_subproject.set(purchase_data.get("subproject", ""))
            self.combo_kd.set(purchase_data.get("kd", ""))
            self.entry_article.insert(0, purchase_data.get("article", ""))
            self.entry_name.insert(0, purchase_data.get("name", ""))
            self.entry_name_eng.insert(0, purchase_data.get("name_eng", ""))
            self.entry_quantity.insert(0, str(purchase_data.get("quantity", "")))
            self.entry_note.insert(0, purchase_data.get("note", ""))
            if purchase_data.get("ordered"):
                self.ordered_var.set(True)
            self.entry_order_date.insert(0, purchase_data.get("order_date", ""))
            if purchase_data.get("received"):
                self.received_var.set(True)
            self.entry_receipt_date.insert(0, purchase_data.get("receipt_date", ""))
            if purchase_data.get("in_order"):
                self.in_order_var.set(True)
            if purchase_data.get("price_request"):
                self.price_request_var.set(True)

        # Кнопки
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=7, pady=15)
        ttk.Button(btn_frame, text="Сохранить", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="История цен", command=self.open_price_history).pack(side=tk.LEFT, padx=5)

        # НОВОЕ: строка подсказки по истории цен
        self.lbl_price_hint = ttk.Label(self, text="", foreground="#0066cc")
        self.lbl_price_hint.grid(row=7, column=0, columnspan=7, sticky="w", padx=10, pady=(0, 8))
        self.update_price_hint()

        # Безопасный захват фокуса (лечит "grab failed: window not viewable")
        self._safe_grab()

    # ------------------------------------------------------------------
    # Безопасный grab
    # ------------------------------------------------------------------
    def _safe_grab(self, attempts=10):
        try:
            if self.winfo_exists() and self.winfo_viewable():
                self.grab_set()
            elif attempts > 0:
                self.after(50, lambda a=attempts - 1: self._safe_grab(a))
        except tk.TclError:
            if attempts > 0:
                self.after(50, lambda a=attempts - 1: self._safe_grab(a))

    # ------------------------------------------------------------------
    # НОВОЕ: история цен по артикулу
    # ------------------------------------------------------------------
    def update_price_hint(self):
        """Показывает последнюю/минимальную цену и отклонение от прошлой закупки."""
        if not hasattr(self, "lbl_price_hint"):
            return
        if not self.db_manager or not hasattr(self.db_manager, "get_price_summary"):
            self.lbl_price_hint.config(text="")
            return
        art = self.entry_article.get().strip()
        if len(art) < 3:
            self.lbl_price_hint.config(text="")
            return
        try:
            s = self.db_manager.get_price_summary(art)
        except Exception:
            s = None
        if not s:
            self.lbl_price_hint.config(text="История цен: нет данных по этому артикулу")
            return
        last = s["last"]
        delta = f" · Δ {s['delta']:+.1f}% к прошлой" if s.get("delta") is not None else ""
        text = (f"Последняя цена: {last['price']:,.2f} {last['currency']} "
                f"({last['supplier'] or '—'}, {last['date'] or '—'}) · "
                f"мин {s['min']:,.2f} ({s['best']['supplier'] or '—'}) · "
                f"записей {s['count']}{delta}").replace(",", " ")
        self.lbl_price_hint.config(text=text)

    def open_price_history(self):
        try:
            from dialogs.price_history_dialog import PriceHistoryDialog
        except ImportError:
            messagebox.showinfo("История цен", "Модуль dialogs/price_history_dialog.py не установлен.")
            return
        PriceHistoryDialog(self, self.db_manager, self.entry_article.get().strip())
        self.update_price_hint()

    # ------------------------------------------------------------------
    # Справочники
    # ------------------------------------------------------------------
    def load_manufacturers(self):
        if self.db_manager:
            m = self.db_manager.get_manufacturers()
            self.combo_manufacturer['values'] = [x['name'] for x in m]

    def load_subprojects(self):
        if self.db_manager:
            s = self.db_manager.get_subprojects(self.project_name)
            self.combo_subproject['values'] = [x['name'] for x in s]

    def load_kd(self):
        if self.db_manager:
            k = self.db_manager.get_kd_directory(self.project_name)
            self.combo_kd['values'] = [x['kd_number'] for x in k]

    # ------------------------------------------------------------------
    # Автоподстановка из номенклатуры
    # ------------------------------------------------------------------
    def on_article_change(self):
        if self.db_manager:
            article = self.entry_article.get()
            if len(article) >= 2:
                results = self.db_manager.search_nomenclature(article, 'article')
                if results:
                    self.combo_manufacturer.set(results[0]['manufacturer'])
                    self.entry_name.delete(0, tk.END)
                    self.entry_name.insert(0, results[0]['name_rus'] or results[0]['name_eng'])
                    self.entry_name_eng.delete(0, tk.END)
                    self.entry_name_eng.insert(0, results[0]['name_eng'] or "")
        self.update_price_hint()

    def on_name_change(self):
        if self.db_manager:
            name = self.entry_name.get()
            if len(name) >= 3:
                results = self.db_manager.search_nomenclature(name, 'name')
                if results:
                    self.entry_article.delete(0, tk.END)
                    self.entry_article.insert(0, results[0]['article'])
                    self.combo_manufacturer.set(results[0]['manufacturer'])
                    self.update_price_hint()

    # ------------------------------------------------------------------
    # Календари
    # ------------------------------------------------------------------
    def select_order_date(self):
        try:
            from dialogs.calendar_dialog import CalendarDialog
            current = self.entry_order_date.get()
            dialog = CalendarDialog(self, current if current else None)
            self.wait_window(dialog)
            if dialog.result:
                self.entry_order_date.delete(0, tk.END)
                self.entry_order_date.insert(0, dialog.result)
        except ImportError:
            self.entry_order_date.delete(0, tk.END)
            self.entry_order_date.insert(0, datetime.now().strftime("%d.%m.%Y"))

    def select_receipt_date(self):
        try:
            from dialogs.calendar_dialog import CalendarDialog
            current = self.entry_receipt_date.get()
            dialog = CalendarDialog(self, current if current else None)
            self.wait_window(dialog)
            if dialog.result:
                self.entry_receipt_date.delete(0, tk.END)
                self.entry_receipt_date.insert(0, dialog.result)
        except ImportError:
            self.entry_receipt_date.delete(0, tk.END)
            self.entry_receipt_date.insert(0, datetime.now().strftime("%d.%m.%Y"))

    # ------------------------------------------------------------------
    # Перевод наименования
    # ------------------------------------------------------------------
    def translate_name(self):
        """Переводит текст из поля 'Наименование (рус)' в 'Наименование (анг)'"""
        russian_text = self.entry_name.get().strip()
        if not russian_text:
            messagebox.showwarning("Внимание", "Поле 'Наименование (рус)' пустое!")
            return

        try:
            self.btn_translate.config(text=" Перевожу...", state="disabled")
            self.update_idletasks()
        except tk.TclError:
            return

        translated = None
        source_used = ""
        try:
            # ШАГ 1: кэш — повторные нажатия не тратят лимит Google
            cache_key = russian_text.lower()
            if cache_key in self.translation_cache:
                translated = self.translation_cache[cache_key]
                source_used = "КЭШ"

            # ШАГ 2: локальный словарь (работает без интернета)
            if not translated:
                translated = self._translate_local(russian_text)
                if translated:
                    source_used = "СЛОВАРЬ"
                    self.translation_cache[cache_key] = translated
                    save_translation_cache(self.translation_cache)

            # ШАГ 3: Google с паузами
            if not translated and HAS_TRANSLATOR:
                translated = self._translate_with_retry(russian_text)
                if translated:
                    source_used = "GOOGLE"
                    self.translation_cache[cache_key] = translated
                    save_translation_cache(self.translation_cache)

            # ШАГ 4: резервный сервис MyMemory, если Google ответил 429
            if not translated and HAS_TRANSLATOR and MyMemoryTranslator is not None:
                translated = self._translate_mymemory(russian_text)
                if translated:
                    source_used = "MYMEMORY"
                    self.translation_cache[cache_key] = translated
                    save_translation_cache(self.translation_cache)

            if not self.winfo_exists():
                return

            if translated:
                self.entry_name_eng.delete(0, tk.END)
                self.entry_name_eng.insert(0, translated)
                print(f"[ПЕРЕВОД] {source_used}: '{russian_text}' -> '{translated}'")
            else:
                messagebox.showwarning(
                    "Перевод недоступен",
                    "Google Translate временно ограничил запросы (слишком много обращений с этого IP),\n"
                    "и резервный сервис также не ответил.\n\n"
                    "Что можно сделать:\n"
                    "1. Подождите 1–2 минуты и нажмите «Перевести» снова;\n"
                    "2. Введите перевод вручную в поле «Наименование (анг)».\n\n"
                    "Успешные переводы сохраняются в кэш и повторно не запрашиваются.")
        except Exception as e:
            print(f"Критическая ошибка перевода: {e}")
            translated = self._translate_local(russian_text)
            if translated and self.winfo_exists():
                try:
                    self.entry_name_eng.delete(0, tk.END)
                    self.entry_name_eng.insert(0, translated)
                except tk.TclError:
                    pass
        finally:
            try:
                if self.winfo_exists() and self.btn_translate.winfo_exists():
                    self.btn_translate.config(text=" Перевести", state="normal")
            except tk.TclError:
                pass

    def _translate_with_retry(self, text, max_retries=2):
        """Google Translate с паузами. При 429 НЕ бросает исключение,
        а возвращает None — вызывающий код переключится на MyMemory."""
        for attempt in range(max_retries):
            try:
                delay = 1.5 + attempt * 2
                print(f"[GOOGLE] Попытка {attempt + 1}/{max_retries}, пауза {delay} с...")
                time.sleep(delay)
                translator = GoogleTranslator(source='ru', target='en')
                result = translator.translate(text)
                if result:
                    return result
            except TooManyRequests:
                print("[GOOGLE] 429: слишком много запросов — переключаемся на резерв")
                return None
            except Exception as e:
                print(f"[GOOGLE] Ошибка попытки {attempt + 1}: {e}")
                if attempt >= max_retries - 1:
                    return None
                time.sleep(2)
        return None

    def _translate_mymemory(self, text):
        """Резервный бесплатный сервис MyMemory.
        ВАЖНО: требует полные коды ru-RU / en-GB, иначе падает
        с 'No support for the provided language'."""
        if MyMemoryTranslator is None:
            return None
        try:
            print("[MYMEMORY] Запрашиваю перевод (ru-RU → en-GB)...")
            translator = MyMemoryTranslator(source='ru-RU', target='en-GB')
            result = translator.translate(text)
            if result:
                result = result.replace('&amp;', '&').replace('&#39;', "'")
                return result
        except Exception as e:
            print(f"[MYMEMORY] Ошибка: {e}")
        return None

    def _translate_local(self, text):
        """Перевод по локальному словарю технических терминов"""
        text_lower = text.lower().strip()
        if text_lower in TECH_DICT:
            return TECH_DICT[text_lower]

        words = text_lower.split()
        translated_words = []
        any_translated = False
        i = 0
        while i < len(words):
            matched = False
            for phrase_len in range(3, 0, -1):
                if i + phrase_len <= len(words):
                    phrase = ' '.join(words[i:i + phrase_len])
                    clean_phrase = phrase.strip('.,;:!?()[]{}"\'')
                    if clean_phrase in TECH_DICT:
                        translated_words.append(TECH_DICT[clean_phrase])
                        any_translated = True
                        i += phrase_len
                        matched = True
                        break
            if not matched:
                word = words[i].strip('.,;:!?()[]{}"\'')
                if word in TECH_DICT:
                    translated_words.append(TECH_DICT[word])
                    any_translated = True
                else:
                    translated_words.append(words[i])
                i += 1

        if any_translated:
            return ' '.join(translated_words)
        return None

    # ------------------------------------------------------------------
    # Сохранение
    # ------------------------------------------------------------------
    def save(self):
        try:
            quantity = int(self.entry_quantity.get()) if self.entry_quantity.get() else 0
        except ValueError:
            messagebox.showwarning("Ошибка", "Некорректное количество!")
            return

        self.result = {
            "number": self.entry_number.get().strip(),
            "manufacturer": self.combo_manufacturer.get().strip(),
            "subproject": self.combo_subproject.get().strip(),
            "kd": self.combo_kd.get().strip(),
            "article": self.entry_article.get().strip(),
            "name": self.entry_name.get().strip(),
            "name_eng": self.entry_name_eng.get().strip(),
            "quantity": quantity,
            "note": self.entry_note.get().strip(),
            "ordered": 1 if self.ordered_var.get() else 0,
            "order_date": self.entry_order_date.get().strip(),
            "received": 1 if self.received_var.get() else 0,
            "receipt_date": self.entry_receipt_date.get().strip(),
            "in_order": 1 if self.in_order_var.get() else 0,
            "price_request": 1 if self.price_request_var.get() else 0,
        }
        self.destroy()