# Правила для сохранения интерфейсов
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}