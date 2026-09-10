"""
代码编辑器 - 带语法高亮、行号、AI 自动补全
基于 QPlainTextEdit 实现（QScintilla 可选）
"""
import os
from typing import Optional

from PySide6.QtWidgets import (
    QPlainTextEdit, QWidget, QCompleter, QLabel,
)
from PySide6.QtCore import Qt, QRect, QSize, QTimer, Signal
from PySide6.QtGui import (
    QFont, QColor, QPainter, QSyntaxHighlighter,
    QTextCharFormat, QKeyEvent,
)

from app.constants import CODE_EXTENSIONS

# 参与 AI 补全的语言
COMPLETABLE_LANGS = {
    "python", "javascript", "typescript", "java", "c", "cpp", "csharp",
    "go", "rust", "ruby", "php", "swift", "kotlin", "scala", "lua", "r",
    "bash", "sql", "css", "html",
}


class LineNumberArea(QWidget):
    """行号区域"""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)


class PythonHighlighter(QSyntaxHighlighter):
    """Python 语法高亮（配色随主题明暗切换）"""

    def __init__(self, document, dark: bool = True):
        super().__init__(document)
        self.dark = dark
        self._init_formats()

    def _init_formats(self):
        if self.dark:
            k, s, c, n, f, cl = "#c792ea", "#c3e88d", "#676e95", "#f78c6c", "#82aaff", "#ffcb6b"
        else:
            k, s, c, n, f, cl = "#8250df", "#22863a", "#6a737d", "#9a6700", "#005cc5", "#e36209"
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(QColor(k))
        self.keyword_format.setFontWeight(QFont.Bold)

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor(s))

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(QColor(c))
        self.comment_format.setFontItalic(True)

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor(n))

        self.function_format = QTextCharFormat()
        self.function_format.setForeground(QColor(f))

        self.class_format = QTextCharFormat()
        self.class_format.setForeground(QColor(cl))
        self.class_format.setFontWeight(QFont.Bold)

        self.keywords = {
            "def", "class", "return", "if", "elif", "else", "for", "while",
            "import", "from", "as", "try", "except", "finally", "with",
            "raise", "pass", "break", "continue", "in", "is", "not", "and",
            "or", "lambda", "yield", "global", "nonlocal", "assert", "del",
            "True", "False", "None", "async", "await",
        }

    def highlightBlock(self, text):
        import re
        # 注释
        comment_match = re.search(r"#.*$", text)
        if comment_match:
            self.setFormat(comment_match.start(), len(text) - comment_match.start(), self.comment_format)
            text = text[:comment_match.start()]

        # 字符串
        for match in re.finditer(r'"[^"]*"|\'[^\']*\'', text):
            self.setFormat(match.start(), match.end() - match.start(), self.string_format)

        # 数字
        for match in re.finditer(r'\b\d+\.?\d*\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self.number_format)

        # 关键字
        for match in re.finditer(r'\b\w+\b', text):
            word = match.group()
            if word in self.keywords:
                self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
            elif word in ("def",):
                # 函数名
                next_match = re.search(r'def\s+(\w+)', text)
                if next_match:
                    self.setFormat(next_match.start(1), next_match.end(1) - next_match.start(1), self.function_format)
            elif word == "class":
                next_match = re.search(r'class\s+(\w+)', text)
                if next_match:
                    self.setFormat(next_match.start(1), next_match.end(1) - next_match.start(1), self.class_format)


class CodeEditor(QPlainTextEdit):
    """代码编辑器"""

    file_saved = Signal(str)
    completion_fetched = Signal(int, object)  # serial, text（工作线程 emit，GUI 槽接收）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file: str = ""
        self.highlighter: Optional[QSyntaxHighlighter] = None
        self._completer: Optional[QCompleter] = None
        self._dark_scheme: bool = True  # 编辑器配色是否适配深色主题
        self._ai_completion_text: str = ""
        self._ai_completion_label: Optional[QLabel] = None

        # AI 补全相关
        self._completion_provider = None      # callable(before, after, language) -> str|None
        self._completion_serial = 0           # 用于丢弃过期结果
        self._completion_enabled = True
        self._suppress_schedule = False
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.setInterval(650)
        self._completion_timer.timeout.connect(self._request_completion_idle)

        self._init_ui()

        self.completion_fetched.connect(self._deliver_completion)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_moved)

    def set_completion_provider(self, provider):
        """设置 AI 补全提供者：provider(code_before, code_after, language) -> str|None"""
        self._completion_provider = provider
        self._completion_serial += 1
        self._hide_ghost()

    def set_ai_completion_enabled(self, enabled: bool):
        self._completion_enabled = bool(enabled)
        if not enabled:
            self._hide_ghost()

    def _init_ui(self):
        self.setFont(QFont("Consolas", 12))
        self.setTabChangesFocus(False)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        # 外观交由主题 QSS 控制（浅色/深色统一），不再内联深色样式

        # 行号区域
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width()

        # AI 补全标签（灰色提示；挂在 viewport 下，与 cursorRect 同一坐标系）
        self._ai_completion_label = QLabel(self.viewport())
        self._ai_completion_label.setStyleSheet("color: #9aa1ad; background: transparent;")
        self._ai_completion_label.hide()

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 20 + digits * self.fontMetrics().horizontalAdvance("9")

    def _update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        # 与主题自适应：浅色/深色都可见的灰色，背景取系统默认（随主题）
        painter.fillRect(event.rect(), self.line_number_area.palette().window().color())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#9aa1ad"))
                painter.drawText(0, int(top), self.line_number_area.width() - 5,
                                 self.fontMetrics().height(), Qt.AlignRight, number)
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            block_number += 1

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(),
                                                  self.line_number_area_width(), cr.height()))

    def open_file(self, path: str):
        """打开文件"""
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                self.setPlainText(f.read())
            self.current_file = path
            self._apply_highlight(path)
        except Exception:
            pass

    def save_file(self):
        """保存文件"""
        if not self.current_file:
            return
        try:
            with open(self.current_file, "w", encoding="utf-8") as f:
                f.write(self.toPlainText())
            self.file_saved.emit(self.current_file)
        except Exception:
            pass

    def set_dark_scheme(self, dark: bool):
        """随主题切换语法高亮配色（浅色/深色）"""
        if bool(dark) == self._dark_scheme:
            return
        self._dark_scheme = bool(dark)
        if self.highlighter is not None:
            self._apply_highlight(self.current_file)

    def _apply_highlight(self, path: str):
        """应用语法高亮（先解除旧高亮器，避免同一文档叠加多个）"""
        if self.highlighter is not None:
            self.highlighter.setDocument(None)
            self.highlighter = None
        ext = os.path.splitext(path)[1].lower()
        lang = CODE_EXTENSIONS.get(ext, "")
        if lang == "python":
            self.highlighter = PythonHighlighter(self.document(), dark=self._dark_scheme)

    # ============ 键盘 ============
    def keyPressEvent(self, event: QKeyEvent):
        # 接受 AI 补全：Tab
        if event.key() == Qt.Key_Tab and not event.modifiers():
            if self._ai_completion_text:
                self.accept_ai_completion()
                return
            self.insertPlainText("    ")
            return
        # 取消 AI 补全：Esc
        if event.key() == Qt.Key_Escape and self._ai_completion_text:
            self._hide_ghost()
            return
        # 手动触发补全：Ctrl+Space
        if event.key() == Qt.Key_Space and (event.modifiers() & Qt.ControlModifier):
            self._hide_ghost()
            self._request_completion_now()
            return
        # Ctrl+S 保存
        if event.key() == Qt.Key_S and (event.modifiers() & Qt.ControlModifier):
            self.save_file()
            return
        super().keyPressEvent(event)

    # ============ AI 补全 ============
    def _current_language(self) -> str:
        if not self.current_file:
            return "plaintext"
        ext = os.path.splitext(self.current_file)[1].lower()
        return CODE_EXTENSIONS.get(ext, "plaintext")

    def _on_text_changed(self):
        if self._suppress_schedule:
            self._suppress_schedule = False
            return
        # 新输入：隐藏旧提示并让在途请求失效，再排一次防抖请求
        self._hide_ghost()
        self._completion_serial += 1
        self._completion_timer.start()

    def _on_cursor_moved(self):
        # 光标移动时隐藏过期的幽灵文本，但保留已请求的补全可稍后显示
        self._hide_ghost()

    def _hide_ghost(self):
        if self._ai_completion_label:
            self._ai_completion_label.hide()
        self._ai_completion_text = ""

    def _request_completion_idle(self):
        self._request_completion_now()

    def _request_completion_now(self):
        if not self._completion_enabled or self._completion_provider is None:
            return
        if not self.current_file:
            return
        lang = self._current_language()
        if lang not in COMPLETABLE_LANGS:
            return
        # 取光标前/后的代码
        cursor = self.textCursor()
        doc = self.document()
        before = doc.toPlainText()[:cursor.position()]
        after = doc.toPlainText()[cursor.position():]
        before = before[-12000:]     # 限制上下文长度
        after = after[:4000]
        if not before.strip():
            return

        self._completion_serial += 1
        serial = self._completion_serial
        provider = self._completion_provider

        def work():
            try:
                text = provider(before, after, lang)
            except Exception:
                text = None
            # 经 Qt 信号投递回 GUI 线程（工作线程的 QTimer.singleShot 不会触发）
            try:
                self.completion_fetched.emit(serial, text)
            except RuntimeError:
                # 编辑器已被销毁
                pass

        import threading
        threading.Thread(target=work, daemon=True).start()

    def _deliver_completion(self, serial: int, text):
        if serial != self._completion_serial:
            return  # 用户已经继续输入，丢弃过期结果
        if not text or not self._completion_enabled:
            return
        text = text.strip("\n").rstrip()
        if not text:
            return
        # 只保留单行以内最有可能的首段补全提示（避免整段文本占据编辑器）
        first_line = text.split("\n", 1)[0]
        if len(first_line) > 200:
            first_line = first_line[:200]
        self.show_ai_completion(first_line)

    def show_ai_completion(self, text: str):
        """显示 AI 补全提示（灰色内联提示）"""
        if not text:
            self._hide_ghost()
            return
        cursor = self.textCursor()
        rect = self.cursorRect(cursor)
        self._ai_completion_label.setText(text)
        self._ai_completion_label.move(rect.right() + 4, rect.top())
        self._ai_completion_label.adjustSize()
        self._ai_completion_label.show()
        self._ai_completion_label.raise_()
        self._ai_completion_text = text

    def accept_ai_completion(self):
        """接受 AI 补全"""
        if self._ai_completion_text:
            self.insertPlainText(self._ai_completion_text)
            self._suppress_schedule = True
            self._hide_ghost()
