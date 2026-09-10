"""侧边栏主组件 - 整合项目管理、文件树、对话列表"""
import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QMenu, QComboBox, QFrame, QFileDialog,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction

from ui.sidebar.file_tree import FileTreeWidget
from ui.sidebar.conversation_list import ConversationListWidget


class SidebarWidget(QWidget):
    """侧边栏"""

    file_opened = Signal(str)
    project_opened = Signal(str)
    conversation_selected = Signal(int)

    def __init__(self, config, database, translator, file_manager=None,
                 git_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = database
        self.tr = translator
        self.file_manager = file_manager
        self.git_manager = git_manager
        self.current_project: str = ""
        self.current_project_id: Optional[int] = None

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部项目选择栏
        top_bar = QFrame()
        top_bar.setObjectName("sideTopBar")
        top_bar.setFixedHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)

        self.project_combo = QComboBox()
        self.project_combo.setObjectName("projectCombo")
        self.project_combo.currentIndexChanged.connect(self._on_project_changed)
        top_layout.addWidget(self.project_combo, 1)

        btn_open = QPushButton("📂")
        btn_open.setFixedSize(28, 28)
        btn_open.setToolTip(self.tr.tr("打开项目"))
        btn_open
        btn_open.clicked.connect(self._open_project)
        top_layout.addWidget(btn_open)

        # Git 操作按钮
        self.btn_git = QPushButton("⎇ Git")
        self.btn_git.setFixedSize(52, 28)
        self.btn_git.setToolTip(self.tr.tr("Git 操作"))
        self.btn_git
        self.btn_git.setEnabled(False)
        self.btn_git.clicked.connect(self._show_git_menu)
        top_layout.addWidget(self.btn_git)

        layout.addWidget(top_bar)

        # Tab 区域
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.South)
        self.tabs

        # 文件树 Tab
        self.file_tree = FileTreeWidget(self.tr)
        self.file_tree.file_opened.connect(self.file_opened.emit)
        self.tabs.addTab(self.file_tree, "📁 文件")

        # 对话列表 Tab
        self.conv_list = ConversationListWidget(self.db, self.tr)
        self.conv_list.conversation_selected.connect(self.conversation_selected.emit)
        self.conv_list.new_conversation.connect(self._new_conversation)
        self.tabs.addTab(self.conv_list, "💬 对话")

        layout.addWidget(self.tabs, 1)

        self._refresh_projects()

    def _refresh_projects(self):
        """刷新项目下拉列表"""
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        self.project_combo.addItem("选择项目...", None)

        # 收藏的项目
        favorites = self.db.list_projects(favorite_only=True)
        fav_paths = {p["path"] for p in favorites}
        if favorites:
            self.project_combo.insertSeparator(self.project_combo.count())
            for p in favorites:
                self.project_combo.addItem(f"⭐ {p['name']}", p["path"])

        # 最近项目（排除已列在收藏中的，避免重复）
        recent = [p for p in self.db.list_projects() if p["path"] not in fav_paths]
        if recent:
            self.project_combo.insertSeparator(self.project_combo.count())
            for p in recent[:10]:
                self.project_combo.addItem(f"🕐 {p['name']}", p["path"])

        self.project_combo.blockSignals(False)
        # 回显当前项目（如有）
        if self.current_project:
            idx = self.project_combo.findData(self.current_project)
            if idx >= 0:
                self.project_combo.blockSignals(True)
                self.project_combo.setCurrentIndex(idx)
                self.project_combo.blockSignals(False)

    def _on_project_changed(self, index):
        path = self.project_combo.itemData(index)
        if path and os.path.exists(path):
            self.set_project(path)

    def set_project(self, path: str):
        """设置当前项目"""
        self.current_project = path
        self._refresh_projects()  # 让下拉框与当前项目保持一致
        self.file_tree.set_root_path(path)

        # 获取项目 ID
        projects = self.db.list_projects()
        for p in projects:
            if p["path"] == path:
                self.current_project_id = p["id"]
                break
        else:
            self.current_project_id = None

        self.conv_list.set_project(self.current_project_id)
        # Git 按钮可用性
        if hasattr(self, "btn_git"):
            is_repo = bool(self.git_manager) and bool(self.git_manager.is_repo(path))
            self.btn_git.setEnabled(is_repo)
        self.project_opened.emit(path)

    def _open_project(self):
        path = QFileDialog.getExistingDirectory(self, self.tr.tr("打开项目"), "")
        if path:
            project_name = os.path.basename(path)
            proj_id = self.db.add_project(project_name, path)
            self.db.update_project_time(proj_id)
            self._refresh_projects()
            self.set_project(path)

    # ============ Git 操作 ============
    def _show_git_menu(self):
        if not self.git_manager or not self.current_project:
            return
        menu = QMenu(self)
        menu
        act_status = QAction(self.tr.tr("Git 状态"), self)
        act_status.triggered.connect(self._git_status)
        menu.addAction(act_status)

        act_log = QAction(self.tr.tr("Git 日志"), self)
        act_log.triggered.connect(self._git_log)
        menu.addAction(act_log)

        menu.addSeparator()
        act_commit = QAction(self.tr.tr("提交更改"), self)
        act_commit.triggered.connect(self._git_commit)
        menu.addAction(act_commit)

        menu.exec(self.btn_git.mapToGlobal(self.btn_git.rect().bottomLeft()))

    def _git_status(self):
        out = self.git_manager.status(self.current_project)
        self._show_text_dialog(self.tr.tr("Git 状态"), out)

    def _git_log(self):
        out = self.git_manager.log(self.current_project, 50)
        self._show_text_dialog(self.tr.tr("Git 日志"), out)

    def _git_commit(self):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        msg, ok = QInputDialog.getText(self, self.tr.tr("提交更改"), self.tr.tr("提交信息:"))
        if ok and msg.strip():
            out = self.git_manager.commit(self.current_project, msg.strip())
            QMessageBox.information(self, self.tr.tr("提交更改"), out)

    def _show_text_dialog(self, title: str, text: str):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(680, 420)
        layout = QVBoxLayout(dlg)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        view
        layout.addWidget(view, 1)
        row = QHBoxLayout()
        row.addStretch()
        btn_close = QPushButton(self.tr.tr("关闭"))
        btn_close.clicked.connect(dlg.accept)
        row.addWidget(btn_close)
        layout.addLayout(row)
        dlg.exec()

    def _new_conversation(self):
        # 触发主窗口的新建对话（通过信号）
        self.conversation_selected.emit(-1)  # -1 表示新建

    def refresh_conversations(self):
        self.conv_list.refresh()

    def refresh_file_tree(self):
        self.file_tree.set_root_path(self.current_project)
