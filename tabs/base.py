class BaseTab:
    """Базовый класс для всех вкладок"""
    def __init__(self, app, parent):
        self.app = app
        self.parent = parent
        self.root = app.root

    @property
    def db_manager(self):
        # Всегда берём актуальное подключение из приложения:
        # после смены базы в настройках вкладки не должны работать
        # со старым (уже закрытым) соединением
        return self.app.db_manager
