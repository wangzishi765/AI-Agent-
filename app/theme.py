"""主题管理 - 根据配置选择并加载全局 QSS 样式"""
import os
from typing import Optional

from app.constants import STYLES_DIR

# 可用主题：文件名映射。未知/旧值统一回退到默认主题（浅色）。
THEMES = {
    "light": "theme_light.qss",
    "tech_dark": "theme.qss",
    "black": "theme_black.qss",
}
DEFAULT_THEME = "light"

# 主题 -> 展示名（展示文本由调用方 tr() 翻译）
THEME_LABELS = {
    "light": "浅色",
    "tech_dark": "科技深色",
    "black": "纯黑",
}


def resolve_theme(theme: Optional[str]) -> str:
    """将存储值规范化为可用主题名"""
    if theme in THEMES:
        return theme
    return DEFAULT_THEME


def get_theme_path(theme: Optional[str]) -> str:
    return os.path.join(STYLES_DIR, THEMES[resolve_theme(theme)])


def load_stylesheet(theme: Optional[str]) -> str:
    """读取主题 QSS 内容；文件缺失时返回空串"""
    path = get_theme_path(theme)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
