"""输入框 - 支持多行输入、快捷键发送、附件、语音、拖拽"""
import os
from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QFileDialog, QFrame, QApplication,
)
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent


class InputBox(QFrame):
    """消息输入框"""

    send_clicked = Signal(str)  # 发送消息
    attach_files = Signal(list)  # 附加文件
    voice_start = Signal()
    voice_stop = Signal()
    ocr_done = Signal(str)  # 粘贴图片 OCR 识别结果

    def __init__(self, translator=None, parent=None):
        super().__init__(parent)
        self.tr = translator
        self.attached_files: List[str] = []
        self._is_voice_recording = False
        self.ocr_engine = None

        self._init_ui()
        self.ocr_done.connect(self._insert_ocr_text)
        self.setAcceptDrops(True)

    def set_ocr_engine(self, engine):
        """启用「粘贴截图 → OCR 转文字」"""
        self.ocr_engine = engine

    def _insert_ocr_text(self, text: str):
        if not text or text.startswith("["):
            return  # 识别为空或返回 "[OCR ...]" 错误提示时不污染输入
        cursor = self.text_edit.textCursor()
        pos = getattr(self, "_ocr_paste_position", None)
        if pos is not None:
            cursor.setPosition(min(pos, len(self.text_edit.toPlainText())))
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)
        self._ocr_paste_position = None

    def _try_ocr_paste(self) -> bool:
        """剪贴板含图片且 OCR 可用时，转后台识别并把文字插入输入框"""
        if self.ocr_engine is None or not self.ocr_engine.is_available():
            return False
        mime = QApplication.clipboard().mimeData()
        if mime is None or not mime.hasImage():
            return False
        engine = self.ocr_engine
        # 记录粘贴时的光标位置，异步结果插回该处
        self._ocr_paste_position = self.text_edit.textCursor().position()

        def work():
            text = engine.recognize_from_clipboard() or ""
            if text.strip() and not text.strip().startswith("["):
                self.ocr_done.emit(text.strip())

        import threading
        threading.Thread(target=work, daemon=True).start()
        return True

    def _init_ui(self):
        # 圆角输入卡片：外观交给主题 QSS（objectName: composeCard）
        self.setObjectName("composeCard")
        # 宽度随窗口/消息列伸缩（由 ChatWidget 统一限宽）
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 10)
        layout.setSpacing(6)

        # 附件预览区
        self.attach_container = QWidget()
        self.attach_container.setObjectName("attachPreviewArea")
        self.attach_preview = QHBoxLayout(self.attach_container)
        self.attach_preview.setContentsMargins(0, 0, 0, 0)
        self.attach_preview.setSpacing(4)
        self.attach_container.hide()
        layout.addWidget(self.attach_container)

        # 输入区
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        # 文本输入
        self.text_edit = QTextEdit()
        self.text_edit.setObjectName("composeEdit")
        self.text_edit.setPlaceholderText(self.tr.tr("输入你的消息...") + "  (Ctrl+Enter 发送)")
        self.text_edit.setFixedHeight(52)
        self.text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.text_edit.textChanged.connect(self._resize_to_fit)
        self.text_edit.installEventFilter(self)
        input_row.addWidget(self.text_edit, 1)

        # 功能按钮：图标 + 可见文字
        def _tool_btn(text, tip):
            b = QPushButton(text)
            b.setObjectName("capBtn")
            b.setFixedHeight(30)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.btn_attach = _tool_btn("📎 " + self.tr.tr("附加文件"), self.tr.tr("附加文件"))
        self.btn_attach.clicked.connect(self._attach_file)

        self.btn_voice = _tool_btn("🎤 " + self.tr.tr("按住说话"), self.tr.tr("按住说话"))
        self.btn_voice.pressed.connect(self._voice_pressed)
        self.btn_voice.released.connect(self._voice_released)

        # 发送按钮
        self.btn_send = QPushButton("发送 ➤")
        self.btn_send.setObjectName("sendBtn")
        self.btn_send.setFixedHeight(34)
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.clicked.connect(self._send)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addLayout(input_row, 1)
        bottom_row.addWidget(self.btn_attach, 0, Qt.AlignBottom)
        bottom_row.addWidget(self.btn_voice, 0, Qt.AlignBottom)
        bottom_row.addWidget(self.btn_send, 0, Qt.AlignBottom)
        layout.addLayout(bottom_row)

    def eventFilter(self, obj, event):
        """事件过滤器：Ctrl+Enter 发送；Ctrl+V 粘贴图片时走 OCR"""
        if obj == self.text_edit and event.type() == QEvent.KeyPress:
            if event.modifiers() & Qt.ControlModifier and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self._send()
                return True
            if (event.modifiers() & Qt.ControlModifier) and not (event.modifiers() & Qt.ShiftModifier) \
                    and event.key() == Qt.Key_V:
                if self._try_ocr_paste():
                    return True
        return super().eventFilter(obj, event)

    def _send(self):
        text = self.text_edit.toPlainText().strip()
        if not text and not self.attached_files:
            return
        self.send_clicked.emit(text)
        self.text_edit.clear()
        self._clear_attachments()

    def _attach_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, self.tr.tr("选择文件"), "", "所有文件 (*.*)")
        if files:
            for f in files:
                self._add_attachment(f)
            self.attach_files.emit(self.attached_files)

    def _add_attachment(self, path: str):
        if path in self.attached_files:
            return
        self.attached_files.append(path)
        self._refresh_attach_preview()

    def _refresh_attach_preview(self):
        # 清空
        while self.attach_preview.count():
            item = self.attach_preview.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.attached_files:
            self.attach_container.hide()
            return

        self.attach_container.show()
        for path in self.attached_files:
            name = os.path.basename(path)
            tag = QPushButton(f"📄 {name} ✕")
            tag.setObjectName("chip")
            tag.setFixedHeight(24)
            tag.setCursor(Qt.PointingHandCursor)
            tag.clicked.connect(lambda checked, p=path: self._remove_attachment(p))
            self.attach_preview.addWidget(tag)
        self.attach_preview.addStretch()

    def _remove_attachment(self, path: str):
        if path in self.attached_files:
            self.attached_files.remove(path)
        self._refresh_attach_preview()

    def _clear_attachments(self):
        self.attached_files.clear()
        self._refresh_attach_preview()

    def _voice_pressed(self):
        self._is_voice_recording = True
        self.btn_voice.setProperty("recording", True)
        self._repolish(self.btn_voice)
        self.voice_start.emit()

    def _voice_released(self):
        if self._is_voice_recording:
            self._is_voice_recording = False
            self.btn_voice.setProperty("recording", False)
            self._repolish(self.btn_voice)
            self.voice_stop.emit()

    def _resize_to_fit(self):
        """输入多行时输入框自动变高（44~180px），删行后自动回缩"""
        try:
            doc = self.text_edit.document()
            h = int(doc.documentLayout().documentSize().height()) + 18
            h = max(52, min(h, 180))
            if h != self.text_edit.height():
                self.text_edit.setFixedHeight(h)
        except Exception:
            pass

    @staticmethod
    def _repolish(widget):
        try:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        except Exception:
            pass

    def insert_text(self, text: str):
        """插入文本到输入框"""
        self.text_edit.insertPlainText(text)

    def get_attached_files(self) -> List[str]:
        return list(self.attached_files)

    # 拖拽支持
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.exists(path):
                self._add_attachment(path)
        if self.attached_files:
            self.attach_files.emit(self.attached_files)
