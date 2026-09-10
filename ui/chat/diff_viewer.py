"""Diff 查看器 - 改前/改后对比，带语法高亮"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QSplitter, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter

from core.diff_engine import DiffEngine


class DiffHighlighter(QSyntaxHighlighter):
    """Diff 语法高亮器"""

    def __init__(self, document):
        super().__init__(document)

    def highlightBlock(self, text):
        if text.startswith("+++") or text.startswith("---"):
            self._set_color(text, "#a78bfa", bold=True)
        elif text.startswith("@@"):
            self._set_color(text, "#fbbf24", bold=True)
        elif text.startswith("+"):
            self._set_color(text, "#34d399")
            self._set_background(text, "#064e3b")
        elif text.startswith("-"):
            self._set_color(text, "#f87171")
            self._set_background(text, "#7f1d1d")

    def _set_color(self, text, color, bold=False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        self.setFormat(0, len(text), fmt)

    def _set_background(self, text, color):
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(color))
        self.setFormat(0, len(text), fmt)


class DiffViewer(QFrame):
    """Diff 对比查看器"""

    def __init__(self, old_text: str, new_text: str, file_path: str = "",
                 translator=None, parent=None):
        super().__init__(parent)
        self.old_text = old_text
        self.new_text = new_text
        self.file_path = file_path
        self.tr = translator
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 头部
        header = QHBoxLayout()
        icon_label = QLabel("📝")
        header.addWidget(icon_label)

        title = QLabel(self.file_path or "文件改动对比")
        title.setStyleSheet("color: #e5e7eb; font-weight: bold; font-size: 13px;")
        header.addWidget(title)
        header.addStretch()

        # 统计
        diff_info = DiffEngine.compare_files(self.old_text, self.new_text)
        stats = QLabel(
            f"+{diff_info['added']}  -{diff_info['removed']}  "
            f"相似度: {diff_info['similarity']}%"
        )
        stats.setStyleSheet("color: #9ca3af; font-size: 11px;")
        header.addWidget(stats)

        layout.addLayout(header)

        # 并排对比
        splitter = QSplitter(Qt.Horizontal)

        # 改前
        old_frame = QFrame()
        old_layout = QVBoxLayout(old_frame)
        old_layout.setContentsMargins(0, 0, 0, 0)
        old_header = QLabel(f"  {self.tr.tr('修改前')}  ")
        old_header.setStyleSheet("background: #7f1d1d; color: #fca5a5; padding: 4px 8px; font-weight: bold; font-size: 11px;")
        old_layout.addWidget(old_header)

        self.old_edit = QTextEdit()
        self.old_edit.setReadOnly(True)
        self.old_edit.setFont(QFont("Consolas", 11))
        self.old_edit.setStyleSheet("""
            QTextEdit { background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
                        border-top: none; padding: 4px; }
        """)
        self.old_edit.setPlainText(self.old_text)
        old_layout.addWidget(self.old_edit)

        # 改后
        new_frame = QFrame()
        new_layout = QVBoxLayout(new_frame)
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_header = QLabel(f"  {self.tr.tr('修改后')}  ")
        new_header.setStyleSheet("background: #064e3b; color: #6ee7b7; padding: 4px 8px; font-weight: bold; font-size: 11px;")
        new_layout.addWidget(new_header)

        self.new_edit = QTextEdit()
        self.new_edit.setReadOnly(True)
        self.new_edit.setFont(QFont("Consolas", 11))
        self.new_edit.setStyleSheet("""
            QTextEdit { background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
                        border-top: none; padding: 4px; }
        """)
        self.new_edit.setPlainText(self.new_text)
        new_layout.addWidget(self.new_edit)

        splitter.addWidget(old_frame)
        splitter.addWidget(new_frame)
        splitter.setSizes([1, 1])

        layout.addWidget(splitter, 1)

        # Unified Diff 视图
        self.diff_edit = QTextEdit()
        self.diff_edit.setReadOnly(True)
        self.diff_edit.setFont(QFont("Consolas", 10))
        self.diff_edit.setMaximumHeight(200)
        self.diff_edit.setStyleSheet("""
            QTextEdit { background: #0d1117; color: #e6edf3; border: 1px solid #30363d;
                        border-radius: 4px; padding: 4px; }
        """)
        unified = DiffEngine.unified_diff(self.old_text, self.new_text)
        self.diff_edit.setPlainText(unified)
        self.highlighter = DiffHighlighter(self.diff_edit.document())

        layout.addWidget(QLabel("Unified Diff:"))
        layout.addWidget(self.diff_edit)

        self.setStyleSheet("""
            DiffViewer { background: #16162a; border: 1px solid #2d2d44; border-radius: 8px; }
        """)
