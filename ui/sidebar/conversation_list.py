"""对话列表组件 - 显示历史对话，支持搜索、标签、收藏"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QLineEdit, QMenu, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction


class ConversationListWidget(QWidget):
    """对话列表"""

    conversation_selected = Signal(int)
    new_conversation = Signal()

    def __init__(self, database, translator=None, parent=None):
        super().__init__(parent)
        self.db = database
        self.tr = translator
        self.current_project_id: Optional[int] = None

        self._init_ui()
        self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 新建按钮
        self.btn_new = QPushButton("+  新对话")
        self.btn_new.setFixedHeight(32)
        self.btn_new
        # clicked 会携带 bool 参数，不能直接 connect 到无参信号
        self.btn_new.clicked.connect(lambda checked=False: self.new_conversation.emit())
        layout.addWidget(self.btn_new)

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索对话...")
        self.search_edit.setFixedHeight(28)
        self.search_edit
        self.search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self.search_edit)

        # 对话列表
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget
        layout.addWidget(self.list_widget, 1)

    def set_project(self, project_id: Optional[int]):
        self.current_project_id = project_id
        self.refresh()

    def refresh(self):
        """刷新对话列表"""
        self.list_widget.clear()
        conversations = self.db.list_conversations(self.current_project_id)
        for conv in conversations:
            item = QListWidgetItem()
            title = conv.get("title", "新对话")
            if conv.get("is_pinned"):
                title = "📌 " + title
            item.setText(title)
            item.setData(Qt.UserRole, conv["id"])
            item.setToolTip(f"创建: {conv.get('created_at', '')}\n更新: {conv.get('updated_at', '')}")
            self.list_widget.addItem(item)

    def _on_search(self, keyword: str):
        if not keyword.strip():
            self.refresh()
            return
        self.list_widget.clear()
        results = self.db.search_conversations(keyword)
        for conv in results:
            item = QListWidgetItem()
            title = conv.get("title", "新对话")
            if conv.get("is_pinned"):
                title = "📌 " + title
            item.setText(title)
            item.setData(Qt.UserRole, conv["id"])
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        conv_id = item.data(Qt.UserRole)
        if conv_id:
            self.conversation_selected.emit(conv_id)

    def _show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        conv_id = item.data(Qt.UserRole)

        menu = QMenu(self)
        menu

        action_rename = QAction(self.tr.tr("重命名"), self)
        action_rename.triggered.connect(lambda: self._rename_conversation(conv_id))
        menu.addAction(action_rename)

        action_pin = QAction(self.tr.tr("置顶/取消置顶"), self)
        action_pin.triggered.connect(lambda: self._toggle_pin(conv_id))
        menu.addAction(action_pin)

        menu.addSeparator()

        action_delete = QAction(self.tr.tr("删除"), self)
        action_delete.triggered.connect(lambda: self._delete_conversation(conv_id))
        menu.addAction(action_delete)

        menu.exec(self.list_widget.viewport().mapToGlobal(pos))

    def _rename_conversation(self, conv_id: int):
        from PySide6.QtWidgets import QInputDialog
        convs = self.db.list_conversations()
        current = next((c for c in convs if c["id"] == conv_id), None)
        old_title = current.get("title", "") if current else ""
        new_title, ok = QInputDialog.getText(self, self.tr.tr("重命名对话"), self.tr.tr("标题:"), text=old_title)
        if ok and new_title:
            self.db.update_conversation(conv_id, title=new_title)
            self.refresh()

    def _toggle_pin(self, conv_id: int):
        convs = self.db.list_conversations()
        current = next((c for c in convs if c["id"] == conv_id), None)
        if current:
            new_pin = 0 if current.get("is_pinned") else 1
            self.db.update_conversation(conv_id, is_pinned=new_pin)
            self.refresh()

    def _delete_conversation(self, conv_id: int):
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, self.tr.tr("删除对话"),
            self.tr.tr("确定删除这个对话吗？此操作不可撤销。"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_conversation(conv_id)
            self.refresh()
