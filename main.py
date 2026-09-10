"""
CodeAgent - 只管代码的 AI Agent
Windows 桌面客户端入口
"""
import sys
import os

# 将项目根目录加入 path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont, QIcon

from app.config import Config
from app.database import Database
from app.i18n import Translator
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CodeAgent")
    app.setOrganizationName("CodeAgent")
    app.setApplicationDisplayName("CodeAgent - 代码智能体")

    # 应用图标（任务栏/窗口/托盘共用）
    from app.constants import ICONS_DIR
    icon_path = os.path.join(ICONS_DIR, "app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 默认字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 初始化核心组件
    config = Config()
    config.load()

    translator = Translator(config.get("language", "zh_CN"))
    translator.install(app)

    database = Database(config.data_dir)
    database.init()

    # 加载主题样式（按配置的 theme 选择 QSS）
    from app.theme import load_stylesheet
    stylesheet = load_stylesheet(config.get("theme"))
    if stylesheet:
        app.setStyleSheet(stylesheet)

    # 创建主窗口
    window = MainWindow(config=config, database=database, translator=translator)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
