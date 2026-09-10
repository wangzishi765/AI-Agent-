"""
主窗口 - CodeAgent 桌面应用主框架
包含：菜单栏、工具栏、侧边栏、对话区、终端、状态栏、系统托盘
"""
import os
import time
import threading
from typing import Optional

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QStatusBar, QToolBar,
    QDockWidget, QSystemTrayIcon, QApplication, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import (
    QAction, QIcon, QKeySequence, QFont, QColor, QPixmap, QPainter,
)

from app.constants import APP_NAME, APP_VERSION, DEFAULT_SHORTCUTS
from core.agent import CodeAgent
from core.file_manager import FileManager
from core.code_executor import CodeExecutor
from core.git_manager import GitManager
from core.formatter import CodeFormatter
from core.diff_engine import DiffEngine
from core.search_engine import SearchEngine
from core.snippet_manager import SnippetManager
from core.ocr import OCREngine
from core.speech import SpeechRecognizer
from models import get_model

from ui.chat.chat_widget import ChatWidget
from ui.sidebar.sidebar import SidebarWidget
from ui.terminal.terminal_widget import TerminalWidget
from ui.editor.code_editor import CodeEditor
from ui.settings.settings_dialog import SettingsDialog
from ui.snippets.snippet_panel import SnippetPanel
from ui.search.search_dialog import SearchDialog
from ui.devtools.devtools_panel import DevToolsPanel


class MainWindow(QMainWindow):
    """CodeAgent 主窗口"""

    # 自定义信号
    project_opened = Signal(str)
    model_changed = Signal(str)
    update_result = Signal(bool, bool, str, str)  # interactive, has_update, latest, info
    update_download_result = Signal(str)          # 安装包路径或空串
    editor_format_done = Signal(str)              # 编辑器格式化结果提示
    global_hotkey_triggered = Signal()            # keyboard 库线程 → 主线程

    def __init__(self, config, database, translator):
        super().__init__()
        self.config = config
        self.db = database
        self.tr = translator

        # 当前项目
        self.current_project: str = ""
        self.current_conversation_id: Optional[int] = None
        # 防止 sidebar.set_project -> project_opened -> _set_project 无限回环
        self._opening_project = False

        # 初始化核心组件
        self._init_core()

        # UI 初始化
        self._init_window()
        self._init_menubar()
        self._init_toolbar()
        self._init_central_widget()
        self._init_docks()
        self._init_statusbar()
        self._init_tray()
        self._init_shortcuts()

        # 连接信号
        self._connect_signals()
        self.update_result.connect(self._on_update_result)
        self.update_download_result.connect(self._on_update_download_result)

        # 启动后检查更新
        if self.config.get("auto_check_update", True):
            QTimer.singleShot(3000, self._auto_check_update)

    def _init_core(self):
        """初始化核心业务组件"""
        self.file_manager = FileManager(self.config)
        self.code_executor = CodeExecutor(self.config)
        self.git_manager = GitManager(self.config)
        self.formatter = CodeFormatter(self.config)
        self.diff_engine = DiffEngine()
        self.search_engine = SearchEngine(self.config)
        self.snippet_manager = SnippetManager(self.db)
        self.ocr_engine = OCREngine(self.config)
        self.speech_recognizer = SpeechRecognizer(self.config)

        # 初始化 AI 模型
        model_type = self.config.get("active_model", "deepseek")
        self.model = get_model(model_type, self.config)

        # 初始化 Agent
        self.agent = CodeAgent(
            model=self.model,
            config=self.config,
            database=self.db,
            file_manager=self.file_manager,
            code_executor=self.code_executor,
            git_manager=self.git_manager,
            search_engine=self.search_engine,
            formatter=self.formatter,
        )

    def _init_window(self):
        """初始化窗口基本属性"""
        self.setWindowTitle(f"{APP_NAME} - {self.tr.tr('代码智能体')} v{APP_VERSION}")
        self.setMinimumSize(1024, 680)
        self.resize(
            self.config.get("window_width", 1400),
            self.config.get("window_height", 900),
        )
        self.setDockOptions(QMainWindow.AllowTabbedDocks | QMainWindow.AnimatedDocks)

    def _init_menubar(self):
        """初始化菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu(self.tr.tr("文件"))
        self.action_new_conv = QAction(self.tr.tr("新对话"), self)
        self.action_new_conv.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("new_conversation", "Ctrl+Shift+N")))
        self.action_new_conv.triggered.connect(self._new_conversation)
        file_menu.addAction(self.action_new_conv)

        file_menu.addSeparator()
        self.action_open_project = QAction(self.tr.tr("打开项目..."), self)
        self.action_open_project.triggered.connect(self._open_project)
        file_menu.addAction(self.action_open_project)

        self.action_open_folder = QAction(self.tr.tr("添加文件夹到工作区..."), self)
        self.action_open_folder.triggered.connect(self._add_workspace_folder)
        file_menu.addAction(self.action_open_folder)

        file_menu.addSeparator()
        self.action_save_file = QAction(self.tr.tr("保存文件"), self)
        self.action_save_file.setShortcut(QKeySequence("Ctrl+S"))
        self.action_save_file.triggered.connect(self._save_current_file)
        file_menu.addAction(self.action_save_file)

        file_menu.addSeparator()
        self.action_export = QAction(self.tr.tr("导出对话..."), self)
        self.action_export.triggered.connect(self._export_conversation)
        file_menu.addAction(self.action_export)

        file_menu.addSeparator()
        self.action_quit = QAction(self.tr.tr("退出"), self)
        self.action_quit.triggered.connect(self._quit_app)
        file_menu.addAction(self.action_quit)

        # 编辑菜单
        edit_menu = menubar.addMenu(self.tr.tr("编辑"))
        self.action_search_files = QAction(self.tr.tr("搜索文件"), self)
        self.action_search_files.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("search_files", "Ctrl+P")))
        self.action_search_files.triggered.connect(self._show_file_search)
        edit_menu.addAction(self.action_search_files)

        self.action_search_code = QAction(self.tr.tr("在文件中搜索"), self)
        self.action_search_code.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("search_code", "Ctrl+Shift+F")))
        self.action_search_code.triggered.connect(self._show_code_search)
        edit_menu.addAction(self.action_search_code)

        edit_menu.addSeparator()
        self.action_settings = QAction(self.tr.tr("设置"), self)
        self.action_settings.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("settings", "Ctrl+,")))
        self.action_settings.triggered.connect(self._show_settings)
        edit_menu.addAction(self.action_settings)

        # 视图菜单
        view_menu = menubar.addMenu(self.tr.tr("视图"))
        self.action_toggle_sidebar = QAction(self.tr.tr("显示/隐藏侧边栏"), self)
        self.action_toggle_sidebar.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("toggle_sidebar", "Ctrl+B")))
        self.action_toggle_sidebar.triggered.connect(self._toggle_sidebar)
        view_menu.addAction(self.action_toggle_sidebar)

        self.action_toggle_terminal = QAction(self.tr.tr("显示/隐藏终端"), self)
        self.action_toggle_terminal.setShortcut(QKeySequence(self.config.get("shortcuts", DEFAULT_SHORTCUTS).get("toggle_terminal", "Ctrl+`")))
        self.action_toggle_terminal.triggered.connect(self._toggle_terminal)
        view_menu.addAction(self.action_toggle_terminal)

        self.action_editor = QAction(self.tr.tr("代码编辑器"), self)
        self.action_editor.triggered.connect(self._show_editor)
        view_menu.addAction(self.action_editor)

        view_menu.addSeparator()
        self.action_snippets = QAction(self.tr.tr("代码片段"), self)
        self.action_snippets.triggered.connect(self._show_snippets)
        view_menu.addAction(self.action_snippets)

        self.action_devtools = QAction(self.tr.tr("开发者工具"), self)
        self.action_devtools.triggered.connect(self._show_devtools)
        view_menu.addAction(self.action_devtools)

        # 帮助菜单
        help_menu = menubar.addMenu(self.tr.tr("帮助"))
        self.action_check_update = QAction(self.tr.tr("检查更新"), self)
        self.action_check_update.triggered.connect(self._check_updates)
        help_menu.addAction(self.action_check_update)

        help_menu.addSeparator()
        self.action_about = QAction(self.tr.tr("关于"), self)
        self.action_about.triggered.connect(self._show_about)
        help_menu.addAction(self.action_about)

    def _init_toolbar(self):
        """初始化工具栏"""
        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # 模型选择
        from PySide6.QtWidgets import QComboBox, QLabel
        toolbar.addWidget(QLabel(f"  {self.tr.tr('模型')}: "))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["DeepSeek", "vLLM 本地"])
        self.model_combo.setCurrentIndex(0 if self.config.get("active_model") == "deepseek" else 1)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        self.model_combo.setFixedWidth(140)
        toolbar.addWidget(self.model_combo)

        toolbar.addSeparator()

        # 新建对话
        self.btn_new_conv = QAction("  +  新对话", self)
        self.btn_new_conv.triggered.connect(self._new_conversation)
        toolbar.addAction(self.btn_new_conv)

        toolbar.addSeparator()

        # 权限模式
        toolbar.addWidget(QLabel(f"  {self.tr.tr('权限')}: "))
        self.permission_combo = QComboBox()
        self.permission_combo.addItems([self.tr.tr("严格"), self.tr.tr("半自动"), self.tr.tr("全自动")])
        perm = self.config.get("permission_mode", "full")
        self.permission_combo.setCurrentIndex({"strict": 0, "semiauto": 1, "full": 2}.get(perm, 2))
        self.permission_combo.currentIndexChanged.connect(self._on_permission_changed)
        self.permission_combo.setFixedWidth(100)
        toolbar.addWidget(self.permission_combo)

        toolbar.addSeparator()

        # 设置按钮
        self.btn_settings = QAction("  ⚙  设置", self)
        self.btn_settings.triggered.connect(self._show_settings)
        toolbar.addAction(self.btn_settings)

    def _init_central_widget(self):
        """初始化中央对话区域"""
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 对话组件
        self.chat_widget = ChatWidget(
            config=self.config,
            db=self.db,
            agent=self.agent,
            translator=self.tr,
            ocr_engine=self.ocr_engine,
            speech_recognizer=self.speech_recognizer,
            file_manager=self.file_manager,
        )
        layout.addWidget(self.chat_widget)

        self.setCentralWidget(central)

    def _init_docks(self):
        """初始化停靠面板（侧边栏、终端等）"""
        # 左侧边栏
        self.sidebar_dock = QDockWidget(self.tr.tr("项目"), self)
        self.sidebar_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.sidebar_widget = SidebarWidget(
            config=self.config, database=self.db, translator=self.tr,
            file_manager=self.file_manager, git_manager=self.git_manager,
        )
        self.sidebar_dock.setWidget(self.sidebar_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sidebar_dock)

        # 底部终端
        self.terminal_dock = QDockWidget(self.tr.tr("终端"), self)
        self.terminal_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)
        self.terminal_widget = TerminalWidget(config=self.config, translator=self.tr)
        self.terminal_dock.setWidget(self.terminal_widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.terminal_dock)
        self.terminal_dock.hide()  # 默认隐藏

    # ============ 内置代码编辑器 ============
    def _build_editor_dock(self):
        """惰性创建编辑器停靠面板（单实例）"""
        if getattr(self, "_editor_dock", None) is not None:
            return
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QLabel, QCheckBox

        editor = CodeEditor(self)
        from app.theme import resolve_theme
        editor.set_dark_scheme(resolve_theme(self.config.get("theme")) in ("tech_dark", "black"))
        editor.set_completion_provider(self._request_code_completion)
        editor.file_saved.connect(self._on_editor_saved)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.editor_path_label = QLabel("")
        self.editor_path_label.setObjectName("editorPath")
        bar.addWidget(self.editor_path_label, 1)

        self.editor_ai_check = QCheckBox(self.tr.tr("AI 补全"))
        self.editor_ai_check.setObjectName("editorAi")
        self.editor_ai_check.setChecked(True)
        self.editor_ai_check.toggled.connect(editor.set_ai_completion_enabled)
        bar.addWidget(self.editor_ai_check)

        btn_format = QPushButton(self.tr.tr("格式化"))
        btn_format.setObjectName("sideBtn")
        btn_format.setFixedHeight(26)
        btn_format.clicked.connect(self._format_current_file)
        bar.addWidget(btn_format)

        btn_save = QPushButton(self.tr.tr("保存"))
        btn_save.setObjectName("primaryBtn")
        btn_save.setFixedHeight(26)
        btn_save.clicked.connect(self._save_current_file)
        bar.addWidget(btn_save)
        layout.addLayout(bar)

        layout.addWidget(editor, 1)

        self.editor_status_label = QLabel("")
        self.editor_status_label.setObjectName("editorStatus")
        layout.addWidget(self.editor_status_label)

        dock = QDockWidget(self.tr.tr("代码编辑器"), self)
        dock.setObjectName("editorDock")
        dock.setAllowedAreas(Qt.RightDockWidgetArea | Qt.LeftDockWidgetArea | Qt.BottomDockWidgetArea)
        dock.setWidget(container)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.hide()
        dock.setAttribute(Qt.WA_DeleteOnClose)
        dock.destroyed.connect(self._clear_editor_dock_ref)

        self._editor_dock = dock
        self._editor = editor

    def _clear_editor_dock_ref(self):
        self._editor_dock = None
        self._editor = None

    def _show_editor(self):
        self._build_editor_dock()
        dock = self._editor_dock
        if dock is None:
            return
        if dock.isVisible():
            dock.hide()
        else:
            dock.show()
            dock.raise_()

    def _open_in_editor(self, path: str):
        """在编辑器里打开文件"""
        if not os.path.isfile(path):
            return
        self._build_editor_dock()
        self._editor.open_file(path)
        self.editor_path_label.setText(os.path.basename(path))
        self.editor_path_label.setToolTip(path)
        self.editor_status_label.setText(path)
        self._editor_dock.show()
        self._editor_dock.raise_()

    def _save_current_file(self):
        ed = getattr(self, "_editor", None)
        if ed is not None and ed.current_file:
            ed.save_file()

    def _on_editor_saved(self, path: str):
        name = os.path.basename(path)
        self.status_bar.showMessage(f"{self.tr.tr('已保存')}: {name}", 3000)
        self.editor_status_label.setText(path)

    def _format_current_file(self):
        ed = getattr(self, "_editor", None)
        if ed is None or not ed.current_file:
            return
        path = ed.current_file

        def worker():
            try:
                result = self.formatter.format_file(path)
                ok = result.get("success", False)
                formatter = result.get("formatter", "")
                err = (result.get("error") or "").strip()
                if ok:
                    msg = f"{self.tr.tr('格式化完成')}: {formatter or path}"
                elif err:
                    msg = f"{self.tr.tr('格式化失败')}: {err[:200]}"
                else:
                    msg = self.tr.tr("格式化完成")
            except Exception as e:
                msg = f"{self.tr.tr('格式化失败')}: {str(e)[:200]}"
            self.editor_format_done.emit(msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_editor_format_done(self, msg: str):
        self.editor_status_label.setText(msg)
        self.status_bar.showMessage(msg, 5000)

    def _request_code_completion(self, before: str, after: str, language: str):
        """CodeEditor 的 AI 补全提供者（在工作线程调用，网络类操作放这里）"""
        model = getattr(self, "model", None)
        if model is None:
            return None
        try:
            name = model.get_model_name()
        except Exception:
            name = ""
        now = time.time()
        cache = getattr(self, "_completion_avail_cache", None)
        if cache is None or cache[0] != name or now - cache[1] > 30:
            try:
                ok = bool(model.is_available())
            except Exception:
                ok = False
            self._completion_avail_cache = (name, now, ok)
        else:
            ok = cache[2]
        if not ok:
            return None
        try:
            from models.completion import CodeCompleter
            return CodeCompleter(model).complete(before, after, language, max_tokens=96)
        except Exception:
            return None

    def _attach_file_to_chat(self, path: str):
        """把文件加入对话输入框的附件（供模型读取上下文）"""
        self.chat_widget.attach_file(path)

    def _init_statusbar(self):
        """初始化状态栏"""
        from PySide6.QtWidgets import QLabel
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_model = QLabel(f"{self.tr.tr('模型')}: DeepSeek")
        self.status_bar.addWidget(self.status_model)

        self.status_project = QLabel(f"{self.tr.tr('项目')}: 未打开")
        self.status_bar.addPermanentWidget(self.status_project)

        self.status_git = QLabel("Git: --")
        self.status_bar.addPermanentWidget(self.status_git)

        self.status_task = QLabel("")
        self.status_bar.addPermanentWidget(self.status_task)

    def _init_tray(self):
        """初始化系统托盘（豆包/GPT 式：关闭驻留、点击恢复）"""
        self.tray_icon = QSystemTrayIcon(self)
        # 优先使用应用图标文件，缺失时才回退为内置绘制图标
        from app.constants import ICONS_DIR
        ico = os.path.join(ICONS_DIR, "app.ico")
        if os.path.exists(ico):
            self.app_icon = QIcon(ico)
        else:
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor("#6366f1"))
            painter = QPainter(pixmap)
            painter.setPen(QColor("white"))
            font = QFont("Segoe UI", 26)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "CA")
            painter.end()
            self.app_icon = QIcon(pixmap)
        self.tray_icon.setIcon(self.app_icon)
        self.tray_icon.setToolTip(f"{APP_NAME} v{APP_VERSION}")

        tray_menu = QMenu()
        action_show = QAction(self.tr.tr("显示窗口"), self)
        action_show.triggered.connect(self._show_window)
        tray_menu.addAction(action_show)

        tray_menu.addSeparator()
        action_quit = QAction(self.tr.tr("退出应用"), self)
        action_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _init_shortcuts(self):
        """初始化快捷键。

        菜单里 QAction 已自带 search_files/search_code/settings/new_conversation
        的快捷键；这里补齐 toggle_terminal/toggle_sidebar，并注册全局召唤热键。
        """
        from PySide6.QtGui import QShortcut
        shortcuts = self.config.get("shortcuts", DEFAULT_SHORTCUTS)

        # 菜单/工具栏 QAction 已注册的快捷键序列，避免重复绑定
        existing = {
            a.shortcut().toString()
            for a in self.findChildren(QAction)
            if a.shortcut() and a.shortcut().toString()
        }

        bindings = {
            "toggle_terminal": self._toggle_terminal,
            "toggle_sidebar": self._toggle_sidebar,
            "settings": self._show_settings,
            "search_files": self._show_file_search,
            "search_code": self._show_code_search,
            "new_conversation": self._new_conversation,
        }
        self._app_shortcuts = []
        for key, slot in bindings.items():
            seq = shortcuts.get(key)
            if not seq:
                continue
            if QKeySequence(seq).toString() in existing:
                continue
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)
            self._app_shortcuts.append(sc)

        # 全局召唤窗口（依赖 keyboard 库，注册失败仅静默降级为应用内功能）
        # keyboard 回调运行在其监听线程，必须经 Qt 信号投递回 GUI 线程
        self.global_hotkey_triggered.connect(self._show_window)
        self._global_hotkey_hook = None
        seq = shortcuts.get("toggle_window", "Ctrl+Alt+C")
        try:
            import keyboard
            self._global_hotkey_hook = keyboard.add_hotkey(
                seq, self.global_hotkey_triggered.emit
            )
        except Exception:
            self._global_hotkey_hook = None

    def _unregister_global_hotkey(self):
        if self._global_hotkey_hook is not None:
            try:
                import keyboard
                keyboard.remove_hotkey(self._global_hotkey_hook)
            except Exception:
                pass
            self._global_hotkey_hook = None

    def _connect_signals(self):
        """连接信号"""
        # 侧边栏信号
        self.sidebar_widget.file_opened.connect(self._on_file_opened)
        self.sidebar_widget.project_opened.connect(self._on_project_opened)
        self.sidebar_widget.conversation_selected.connect(self._on_conversation_selected)
        self.sidebar_widget.file_tree.file_attach_requested.connect(self._attach_file_to_chat)

        # 对话组件信号
        self.chat_widget.task_started.connect(self._on_task_started)
        self.chat_widget.task_finished.connect(self._on_task_finished)
        self.chat_widget.conversation_created.connect(self._on_conversation_created)

        # 编辑器
        self.editor_format_done.connect(self._on_editor_format_done)

    # ============ 事件处理 ============
    def closeEvent(self, event):
        """关闭事件"""
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable() and not self.tray_icon.icon().isNull()
        if self.config.get("close_to_tray", True) and tray_ok:
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                APP_NAME,
                self.tr.tr("应用已最小化到系统托盘"),
                QSystemTrayIcon.Information,
                2000,
            )
        else:
            self._quit_app()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    # ============ 动作 ============
    def _new_conversation(self):
        """新建对话"""
        title = self.tr.tr("新对话")
        conv_id = self.db.create_conversation(
            project_id=self._get_current_project_id(),
            title=title,
            model=self.config.get("active_model", "deepseek"),
        )
        self.current_conversation_id = conv_id
        self.chat_widget.load_conversation(conv_id)
        self.sidebar_widget.refresh_conversations()

    def _open_project(self):
        """打开项目"""
        path = QFileDialog.getExistingDirectory(self, self.tr.tr("打开项目"), "")
        if path:
            self._set_project(path)

    def _add_workspace_folder(self):
        """添加文件夹到工作区"""
        path = QFileDialog.getExistingDirectory(self, self.tr.tr("添加文件夹"), "")
        if path:
            folders = self.config.get("workspace_folders", [])
            if path not in folders:
                folders.append(path)
                self.config.set("workspace_folders", folders)
            self.sidebar_widget.refresh_file_tree()

    def _set_project(self, path: str):
        """设置当前项目（带重入保护，避免 sidebar.project_opened 信号回环）"""
        if self._opening_project:
            return
        if path == self.current_project and self.sidebar_widget.current_project == path:
            return
        self._opening_project = True
        try:
            self.current_project = path
            self.agent.set_project(path)
            project_name = os.path.basename(path)

            # 记录到数据库
            proj_id = self.db.add_project(project_name, path)
            self.db.update_project_time(proj_id)

            # 更新 UI
            self.status_project.setText(f"{self.tr.tr('项目')}: {project_name}")
            self.sidebar_widget.set_project(path)
            self.chat_widget.set_project(path)

            # 更新 Git 状态
            if self.git_manager.is_repo(path):
                self.status_git.setText("Git: 已初始化")
            else:
                self.status_git.setText("Git: 非仓库")

            self.project_opened.emit(path)

            # 项目已切换：开启一个属于新项目的新会话，避免消息落到旧项目会话
            self._new_conversation()
        finally:
            self._opening_project = False

    def _get_current_project_id(self) -> Optional[int]:
        if not self.current_project:
            return None
        projects = self.db.list_projects()
        for p in projects:
            if p["path"] == self.current_project:
                return p["id"]
        return None

    def _on_model_changed(self, index: int):
        model_type = "deepseek" if index == 0 else "vllm_local"
        self.config.set("active_model", model_type)
        self.model = get_model(model_type, self.config)
        self.agent.model = self.model
        self._completion_avail_cache = None  # 清掉可用性缓存
        self.status_model.setText(f"{self.tr.tr('模型')}: {'DeepSeek' if index == 0 else 'vLLM本地'}")
        self.model_changed.emit(model_type)

    def _on_permission_changed(self, index: int):
        modes = ["strict", "semiauto", "full"]
        self.config.set("permission_mode", modes[index])

    def _on_file_opened(self, path: str):
        """文件被打开（在编辑器打开）"""
        self._open_in_editor(path)

    def _on_project_opened(self, path: str):
        self._set_project(path)

    def _on_conversation_selected(self, conv_id: int):
        if conv_id == -1:
            # 侧边栏“新对话”按钮通过 -1 请求新建
            self._new_conversation()
            return
        self.current_conversation_id = conv_id
        self.chat_widget.load_conversation(conv_id)

    def _on_conversation_created(self, conv_id: int):
        self.current_conversation_id = conv_id
        self.sidebar_widget.refresh_conversations()

    def _on_task_started(self, task):
        self.status_task.setText(f"{self.tr.tr('运行中...')} ({task.duration}s)")

    def _on_task_finished(self, task):
        if task.status == "success":
            self.status_task.setText(f"{self.tr.tr('完成')} - {task.duration}s")
        else:
            self.status_task.setText(f"{self.tr.tr('失败')} - {task.duration}s")
        QTimer.singleShot(5000, lambda: self.status_task.setText(""))

    def _toggle_sidebar(self):
        self.sidebar_dock.setVisible(not self.sidebar_dock.isVisible())

    def _toggle_terminal(self):
        self.terminal_dock.setVisible(not self.terminal_dock.isVisible())

    def _show_settings(self):
        dialog = SettingsDialog(self.config, self.tr, self)
        if dialog.exec():
            # 应用设置变更
            self._apply_settings()

    def _apply_settings(self):
        """应用设置变更"""
        # 语言变更需要重启（此处不处理）
        # 主题即时生效
        try:
            from app.theme import load_stylesheet, resolve_theme
            from PySide6.QtWidgets import QApplication
            theme_name = resolve_theme(self.config.get("theme"))
            qapp = QApplication.instance()
            if qapp is not None:
                qapp.setStyleSheet(load_stylesheet(theme_name))
            ed = getattr(self, "_editor", None)
            if ed is not None:
                ed.set_dark_scheme(theme_name in ("tech_dark", "black"))
        except Exception:
            pass
        # 模型：设置保存后重建实例，让 API Key/Base/模型名等改动即时生效
        model_type = self.config.get("active_model", "deepseek")
        idx = 0 if model_type == "deepseek" else 1
        self.model_combo.setCurrentIndex(idx)
        self.model = get_model(model_type, self.config)
        self.agent.model = self.model
        self._completion_avail_cache = None
        self.status_model.setText(f"{self.tr.tr('模型')}: {'DeepSeek' if idx == 0 else 'vLLM本地'}")

    def _show_snippets(self):
        """显示代码片段面板（单实例，避免重复创建堆积）"""
        if getattr(self, "snippets_dock", None) is not None:
            self.snippets_dock.show()
            self.snippets_dock.raise_()
            return
        self.snippets_dock = QDockWidget(self.tr.tr("代码片段"), self)
        panel = SnippetPanel(self.snippet_manager, self.tr, self)
        panel.snippet_inserted.connect(self.chat_widget.insert_text)
        self.snippets_dock.setWidget(panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.snippets_dock)
        self.snippets_dock.setAttribute(Qt.WA_DeleteOnClose)
        self.snippets_dock.destroyed.connect(self._clear_snippets_dock_ref)

    def _clear_snippets_dock_ref(self):
        self.snippets_dock = None

    def _show_devtools(self):
        """显示开发者工具（单实例，避免重复创建堆积）"""
        if getattr(self, "devtools_dock", None) is not None:
            self.devtools_dock.show()
            self.devtools_dock.raise_()
            return
        self.devtools_dock = QDockWidget(self.tr.tr("开发者工具"), self)
        panel = DevToolsPanel(self.db, self.tr, self)
        self.devtools_dock.setWidget(panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.devtools_dock)
        self.devtools_dock.setAttribute(Qt.WA_DeleteOnClose)
        self.devtools_dock.destroyed.connect(self._clear_devtools_dock_ref)

    def _clear_devtools_dock_ref(self):
        self.devtools_dock = None

    def _show_file_search(self):
        dialog = SearchDialog(self.search_engine, self.current_project, "files", self.tr, self)
        dialog.file_selected.connect(self._on_file_opened)
        dialog.exec()

    def _show_code_search(self):
        dialog = SearchDialog(self.search_engine, self.current_project, "code", self.tr, self)
        dialog.file_selected.connect(self._on_file_opened)
        dialog.exec()

    def _export_conversation(self):
        if not self.current_conversation_id:
            QMessageBox.warning(self, APP_NAME, self.tr.tr("没有可导出的对话"))
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr.tr("导出对话"), "conversation.md",
            "Markdown (*.md);;JSON (*.json);;PDF (*.pdf)"
        )
        if path:
            messages = self.db.list_messages(self.current_conversation_id)
            if path.endswith(".json"):
                import json
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(messages, f, ensure_ascii=False, indent=2)
            elif path.endswith(".pdf"):
                ok, err = self._export_conversation_pdf(messages, path)
                if not ok:
                    QMessageBox.warning(self, APP_NAME, err)
                    return
            else:
                user_label = self.tr.tr("用户")
                assistant_label = self.tr.tr("助手")
                with open(path, "w", encoding="utf-8") as f:
                    for msg in messages:
                        role = user_label if msg["role"] == "user" else assistant_label
                        f.write(f"## {role}\n\n{msg['content']}\n\n---\n\n")
            QMessageBox.information(self, APP_NAME, f"{self.tr.tr('已导出到')}: {path}")

    def _export_conversation_pdf(self, messages, path: str):
        """把对话导出为 PDF（基于 Qt 文档打印，无额外依赖）"""
        try:
            from PySide6.QtPrintSupport import QPrinter
            from PySide6.QtGui import QTextDocument
            from ui.chat.message_bubble import render_markdown

            user_label = self.tr.tr("用户")
            assistant_label = self.tr.tr("助手")
            parts = ['<html><head><meta charset="utf-8"></head><body>']
            for msg in messages:
                if msg.get("msg_type") == "tool_result":
                    continue
                role = user_label if msg.get("role") == "user" else assistant_label
                color = "#2563eb" if msg.get("role") == "user" else "#7c3aed"
                content = (msg.get("content") or "").replace("\u0000", "")
                parts.append(
                    f'<h3 style="color:{color};border-bottom:1px solid #ddd;'
                    f'padding-bottom:4px;">{role}</h3>'
                    f'{render_markdown(content)}'
                )
            parts.append("</body></html>")

            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            doc = QTextDocument()
            doc.setHtml("".join(parts))
            doc.print_(printer)
            return True, ""
        except Exception as e:
            return False, str(e)

    def _auto_check_update(self):
        """启动时的静默更新检查"""
        self._run_update_check(interactive=False)

    def _check_updates(self):
        """手动检查更新（菜单）"""
        self._run_update_check(interactive=True)

    def _run_update_check(self, interactive: bool = False):
        """在后台线程检查更新，结果经信号回主线程显示"""
        try:
            from app.updater import Updater
        except Exception:
            return
        updater = Updater(self.config)
        self.status_task.setText(self.tr.tr("正在检查更新..."))

        def worker():
            try:
                has_update, latest, info = updater.check_for_updates()
            except Exception as e:
                has_update, latest, info = False, "", str(e)
            self.update_result.emit(interactive, has_update, latest, info)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_result(self, interactive: bool, has_update: bool, latest: str, info: str):
        """GUI 线程：处理更新检查结果"""
        if has_update:
            msg = f"{self.tr.tr('发现新版本')}: v{latest}"
            self.status_task.setText(msg)
            if interactive:
                reply = QMessageBox.question(
                    self, APP_NAME, f"{msg}\n\n{self.tr.tr('是否立即下载并安装更新？')}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._download_and_install(latest)
        else:
            # 检查失败等错误信息原样呈现，不要误报“已是最新版本”
            if info and any(k in info for k in ("检查失败", "未安装", "HTTP", "错误", "error")):
                self.status_task.setText(info)
                if interactive:
                    QMessageBox.information(self, APP_NAME, info)
            else:
                self.status_task.setText(self.tr.tr("已是最新版本"))
                if interactive:
                    QMessageBox.information(self, APP_NAME, self.tr.tr("当前已是最新版本"))
        QTimer.singleShot(6000, lambda: self.status_task.setText(""))

    def _download_and_install(self, version: str):
        """后台下载安装包，成功后静默安装并退出"""
        self.status_task.setText(self.tr.tr("正在下载更新..."))

        def worker():
            path = ""
            try:
                from app.updater import Updater
                updater = Updater(self.config)
                path = updater.download_update(version) or ""
            except Exception:
                path = ""
            self.update_download_result.emit(path)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_download_result(self, path: str):
        if not path or not os.path.exists(path):
            self.status_task.setText(self.tr.tr("更新下载失败，请稍后重试"))
            return
        try:
            from app.updater import Updater
            if Updater(self.config).apply_update(path):
                self._unregister_global_hotkey()
                QTimer.singleShot(300, lambda: QApplication.instance() and QApplication.instance().quit())
        except Exception:
            self.status_task.setText(self.tr.tr("更新下载失败，请稍后重试"))

    def _show_about(self):
        QMessageBox.about(
            self,
            f"{self.tr.tr('关于')} {APP_NAME}",
            f"<h3>{APP_NAME} v{APP_VERSION}</h3>"
            f"<p>{self.tr.tr('只管代码的 AI Agent')}</p>"
            f"<p>Python + PySide6 + DeepSeek + vLLM</p>"
            f"<p>&copy; 2026 CodeAgent</p>",
        )

    def _quit_app(self):
        """退出应用"""
        self._unregister_global_hotkey()
        self.tray_icon.hide()
        try:
            self.config.save()
        finally:
            try:
                self.db.close()
            except Exception:
                pass
        QApplication.quit()
