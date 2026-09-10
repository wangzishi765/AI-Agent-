"""多语言翻译器"""
import importlib
from typing import Dict, Optional

from PySide6.QtCore import QTranslator, QLocale


class Translator:
    """简单的基于字典的翻译器，支持中英日韩"""

    def __init__(self, language: str = "zh_CN"):
        self.language = language
        self._translations: Dict[str, str] = {}
        self._qt_translator: Optional[QTranslator] = None
        self.load(language)

    def load(self, language: str):
        self.language = language
        try:
            mod = importlib.import_module(f"app.i18n.{language}")
            self._translations = getattr(mod, "TRANSLATIONS", {})
        except (ImportError, AttributeError):
            self._translations = {}

    def tr(self, text: str, **kwargs) -> str:
        """翻译文本，支持格式化占位符"""
        translated = self._translations.get(text, text)
        if kwargs:
            try:
                translated = translated.format(**kwargs)
            except (KeyError, IndexError):
                pass
        return translated

    def install(self, app):
        """安装 Qt 翻译器（用于内置控件的本地化）"""
        if self._qt_translator is None:
            self._qt_translator = QTranslator()
        locale_map = {
            "zh_CN": QLocale.Chinese,
            "en_US": QLocale.English,
            "ja_JP": QLocale.Japanese,
            "ko_KR": QLocale.Korean,
        }
        lang = locale_map.get(self.language, QLocale.Chinese)
        self._qt_translator.load(QLocale(lang), "qtbase", "_", "")
        app.installTranslator(self._qt_translator)

    def available_languages(self) -> Dict[str, str]:
        from app.constants import LANGUAGES
        return LANGUAGES
