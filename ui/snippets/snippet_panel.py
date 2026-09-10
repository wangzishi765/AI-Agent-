"""代码片段管理面板 - 分类、搜索、插入、编辑"""
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QComboBox, QTextEdit, QSplitter, QInputDialog,
    QMessageBox, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class SnippetPanel(QWidget):
    """代码片段面板"""

    snippet_inserted = Signal(str)

    def __init__(self, snippet_manager, translator, parent=None):
        super().__init__(parent)
        self.manager = snippet_manager
        self.tr = translator
        self.current_snippet_id: Optional[int] = None
        self._init_ui()
        self._refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 工具栏
        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("+ 新建")
        self.btn_add.setFixedHeight(28)
        self.btn_add
        self.btn_add.clicked.connect(self._add_snippet)
        toolbar.addWidget(self.btn_add)

        self.btn_delete = QPushButton("🗑 删除")
        self.btn_delete.setFixedHeight(28)
        self.btn_delete
        self.btn_delete.clicked.connect(self._delete_snippet)
        toolbar.addWidget(self.btn_delete)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 搜索和分类
        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索片段...")
        self.search_edit.setFixedHeight(28)
        self.search_edit
        self.search_edit.textChanged.connect(self._refresh)
        search_row.addWidget(self.search_edit, 1)

        self.category_combo = QComboBox()
        self.category_combo.setFixedHeight(28)
        self.category_combo
        self.category_combo.currentIndexChanged.connect(self._refresh)
        search_row.addWidget(self.category_combo)
        layout.addLayout(search_row)

        # 分割：列表 + 编辑器
        splitter = QSplitter(Qt.Vertical)

        # 片段列表
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.NoFrame)
        self.list_widget
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        splitter.addWidget(self.list_widget)

        # 编辑器
        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 8, 0, 0)
        editor_layout.setSpacing(4)

        # 标题和语言
        info_row = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(self.tr.tr("片段标题"))
        self.title_edit.setFixedHeight(28)
        self.title_edit
        info_row.addWidget(self.title_edit, 1)

        self.lang_edit = QLineEdit()
        self.lang_edit.setPlaceholderText("语言")
        self.lang_edit.setFixedWidth(80)
        self.lang_edit.setFixedHeight(28)
        self.lang_edit.setStyleSheet(self.title_edit.styleSheet())
        info_row.addWidget(self.lang_edit)
        editor_layout.addLayout(info_row)

        # 代码编辑
        self.code_edit = QTextEdit()
        self.code_edit.setFont(QFont("Consolas", 11))
        self.code_edit.setPlaceholderText(self.tr.tr("代码内容"))
        self.code_edit
        editor_layout.addWidget(self.code_edit, 1)

        # 按钮
        btn_row = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存")
        self.btn_save.setFixedHeight(28)
        self.btn_save
        self.btn_save.clicked.connect(self._save_snippet)
        btn_row.addWidget(self.btn_save)

        self.btn_insert = QPushButton("📋 插入到对话")
        self.btn_insert.setFixedHeight(28)
        self.btn_insert
        self.btn_insert.clicked.connect(self._insert_snippet)
        btn_row.addWidget(self.btn_insert)
        btn_row.addStretch()
        editor_layout.addLayout(btn_row)

        splitter.addWidget(editor_widget)
        splitter.setSizes([200, 300])
        layout.addWidget(splitter, 1)

    def _refresh(self):
        self.list_widget.clear()
        keyword = self.search_edit.text().strip()
        category = self.category_combo.currentText()
        if category == self.tr.tr("全部分类"):
            category = None

        snippets = self.manager.get_all(category, keyword)
        for s in snippets:
            item = QListWidgetItem()
            lang = s.get("language", "")
            title = s.get("title", "")
            item.setText(f"[{lang}] {title}" if lang else title)
            item.setData(Qt.UserRole, s["id"])
            self.list_widget.addItem(item)

        # 刷新分类
        current = self.category_combo.currentText()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem(self.tr.tr("全部分类"))
        for cat in self.manager.get_categories():
            self.category_combo.addItem(cat)
        idx = self.category_combo.findText(current)
        if idx >= 0:
            self.category_combo.setCurrentIndex(idx)
        self.category_combo.blockSignals(False)

    def _on_item_clicked(self, item):
        snippet_id = item.data(Qt.UserRole)
        self.current_snippet_id = snippet_id
        snippets = self.manager.get_all()
        for s in snippets:
            if s["id"] == snippet_id:
                self.title_edit.setText(s.get("title", ""))
                self.lang_edit.setText(s.get("language", ""))
                self.code_edit.setPlainText(s.get("content", ""))
                break

    def _add_snippet(self):
        title, ok = QInputDialog.getText(self, self.tr.tr("新建片段"), self.tr.tr("标题:"))
        if ok and title:
            snippet_id = self.manager.add(title, "", "text", "默认")
            self.current_snippet_id = snippet_id
            self._refresh()
            self.title_edit.setText(title)
            self.code_edit.setFocus()

    def _save_snippet(self):
        if not self.current_snippet_id:
            return
        self.manager.update(
            self.current_snippet_id,
            title=self.title_edit.text(),
            language=self.lang_edit.text(),
            content=self.code_edit.toPlainText(),
        )
        self._refresh()
        QMessageBox.information(self, self.tr.tr("保存"), self.tr.tr("片段已保存"))

    def _delete_snippet(self):
        if not self.current_snippet_id:
            return
        reply = QMessageBox.question(
            self, self.tr.tr("删除"), self.tr.tr("确定删除这个片段吗？"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.manager.delete(self.current_snippet_id)
            self.current_snippet_id = None
            self.title_edit.clear()
            self.lang_edit.clear()
            self.code_edit.clear()
            self._refresh()

    def _insert_snippet(self):
        code = self.code_edit.toPlainText()
        if code:
            self.snippet_inserted.emit(code)
