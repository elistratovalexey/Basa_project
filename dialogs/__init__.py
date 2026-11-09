# Пакет dialogs - модули диалоговых окон приложения
from dialogs.calendar_dialog import CalendarDialog
from dialogs.order_dialog import OrderDialog, OrderItemEditDialog
from dialogs.purchase_dialog import PurchaseDialog
from dialogs.specification_dialog import SpecificationDialog
from dialogs.payment_dialog import PaymentDialog
from dialogs.nomenclature_dialog import NomenclatureDialog
from dialogs.manufacturer_dialog import ManufacturerDialog
from dialogs.subproject_dialog import SubprojectDialog
from dialogs.kd_dialog import KDDialog
from dialogs.nomenclature_search_dialog import NomenclatureSearchDialog
from dialogs.file_import_dialog import FileImportMatchDialog

__all__ = [
    'CalendarDialog',
    'OrderDialog',
    'OrderItemEditDialog',
    'PurchaseDialog',
    'SpecificationDialog',
    'PaymentDialog',
    'NomenclatureDialog',
    'ManufacturerDialog',
    'SubprojectDialog',
    'KDDialog',
    'NomenclatureSearchDialog',
    'FileImportMatchDialog',
]