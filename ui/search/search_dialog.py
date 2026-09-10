"""搜索对话框 - 文件名搜索 + 全局代码内容搜索"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QLabel, QPushButton, QComboBox, QCheckBox,
    QFrame, QSplitter, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont


class SearchDialog(QDialog):
    """搜索对话框"""

    file_selected = Signal(str)
    search_finished = Signal(int, object)  # serial, rows

    def __init__(self, search_engine, project_root: str, mode: str = "files",
                 translator=None, parent=None):
        super().__init__(parent)
        self.search_engine = search_engine
        self.project_root = project_root
        self.mode = mode  # "files" or "code"
        self.tr = translator
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._do_search)
        self._search_serial = 0
        self.search_finished.connect(self._on_search_finished)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle(self.tr.tr("搜索"))
        self.setMinimumSize(700, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 搜索输入
        input_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        placeholder = self.tr.tr("输入文件名搜索... (Ctrl+P)") if self.mode == "files" else self.tr.tr("输入要搜索的代码内容... (Ctrl+Shift+F)")
        self.search_edit.setPlaceholderText(placeholder)
        self.search_edit.setFixedHeight(36)
        self.search_edit
        self.search_edit.textChanged.connect(self._on_text_changed)
        input_row.addWidget(self.search_edit, 1)

        # 模式切换
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([self.tr.tr("文件名"), self.tr.tr("代码内容")])
        self.mode_combo.setCurrentIndex(0 if self.mode == "files" else 1)
        self.mode_combo.setFixedHeight(36)
        self.mode_combo
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        input_row.addWidget(self.mode_combo)

        layout.addLayout(input_row)

        # 选项
        options_row = QHBoxLayout()
        self.case_sensitive = QCheckBox(self.tr.tr("区分大小写"))
        self.case_sensitive.setStyleSheet("color: #9ca3af;")
        options_row.addWidget(self.case_sensitive)

        self.use_regex = QCheckBox(self.tr.tr("正则表达式"))
        self.use_regex.setStyleSheet("color: #9ca3af;")
        options_row.addWidget(self.use_regex)
        options_row.addStretch()

        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #6b7280; font-size: 12px;")
        options_row.addWidget(self.result_label)
        layout.addLayout(options_row)

        # 结果区
        splitter = QSplitter(Qt.Horizontal)

        self.result_list = QListWidget()
        self.result_list.setFrameShape(QFrame.NoFrame)
        self.result_list
        self.result_list.itemClicked.connect(self._on_result_clicked)
        self.result_list.itemDoubleClicked.connect(self._on_result_double_clicked)
        splitter.addWidget(self.result_list)

        # 预览
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFont(QFont("Consolas", 11))
        self.preview
        splitter.addWidget(self.preview)
        splitter.setSizes([300, 400])

        layout.addWidget(splitter, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton(self.tr.tr("关闭"))
        btn_close.setFixedHeight(32)
        btn_close
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        btn_open = QPushButton(self.tr.tr("打开"))
        btn_open.setFixedHeight(32)
        btn_open
        btn_open.clicked.connect(self._open_selected)
        btn_row.addWidget(btn_open)
        layout.addLayout(btn_row)

        self.search_edit.setFocus()

    def _on_text_changed(self, text):
        self._debounce_timer.start(300)

    def _on_mode_changed(self, index):
        self.mode = "files" if index == 0 else "code"
        self._do_search()

    def _do_search(self):
        query = self.search_edit.text().strip()
        if not query or not self.project_root:
            self.result_list.clear()
            self.result_label.setText("")
            return

        self.result_list.clear()
        serial = self._search_serial + 1
        self._search_serial = serial
        root = self.project_root
        mode = self.mode
        case = self.case_sensitive.isChecked()
        regex = self.use_regex.isChecked()
        engine = self.search_engine
        self.result_label.setText(self.tr.tr("搜索中..."))

        def work():
            rows = []
            try:
                if mode == "files":
                    results = engine.search_files(root, query, limit=100)
                    for r in results:
                        rows.append({
                            "kind": "f",
                            "label": r.get("relative_path") or r.get("name", ""),
                            "path": r["path"],
                            "lines": [],
                        })
                else:
                    results = engine.search_code(root, query, limit=50,
                                                 case_sensitive=case, use_regex=regex)
                    for r in results:
                        lines = [(m["line"], m["content"]) for m in (r.get("matches") or [])]
                        rows.append({
                            "kind": "c",
                            "label": f"{r.get('relative_path', '')} ({len(lines)} 处)",
                            "path": r["path"],
                            "lines": lines[:40],
                        })
            except Exception:
                rows = None
            self.search_finished.emit(serial, rows)

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _on_search_finished(self, serial: int, rows):
        """GUI 线程：接收搜索结果（过期请求直接丢弃）"""
        if serial != self._search_serial:
            return
        self.result_list.clear()
        if rows is None:
            self.result_label.setText(self.tr.tr("搜索失败"))
            return
        for r in rows:
            item = QListWidgetItem()
            item.setText(r["label"])
            item.setData(Qt.UserRole, r["path"])
            item.setData(Qt.UserRole + 1, r.get("lines") or [])
            item.setData(Qt.UserRole + 2, r["kind"])
            self.result_list.addItem(item)
        if rows:
            if self.mode == "files":
                self.result_label.setText(f"{len(rows)} 个文件")
            else:
                total = sum(len(r["lines"]) for r in rows)
                self.result_label.setText(f"{len(rows)} 个文件，{total} 处匹配")
        else:
            self.result_label.setText(self.tr.tr("无匹配结果"))

    def _on_result_clicked(self, item):
        path = item.data(Qt.UserRole)
        lines = item.data(Qt.UserRole + 1) or []
        kind = item.data(Qt.UserRole + 2) or "f"
        if kind == "c" and lines:
            preview_text = "".join(f"行 {ln}: {content}\n" for ln, content in lines[:20])
            self.preview.setPlainText(preview_text)
            return
        # 文件模式：预览文件内容
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                self.preview.setPlainText(f.read()[:5000])
        except Exception:
            self.preview.setPlainText("无法预览")

    def _on_result_double_clicked(self, item):
        self._open_selected()

    def _open_selected(self):
        item = self.result_list.currentItem()
        if item:
            path = item.data(Qt.UserRole)
            if path:
                self.file_selected.emit(path)
                self.accept()
