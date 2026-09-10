"""消息气泡 - DeepSeek/豆包风格：用户消息右侧蓝气泡，助手左侧白气泡带头像"""
import re
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser,
    QFrame, QPushButton,
)
from PySide6.QtCore import Qt, Signal


def render_markdown(text: str) -> str:
    """简易 Markdown 渲染为 HTML（模块级函数，供气泡与导出 PDF 复用）。

    先把围栏代码块摘出并原样输出，再对普通文本做轻量 markdown，
    避免把代码里的 **、*、### 等误当成格式标记。
    """
    # 转义 HTML
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    fence = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
    parts = []  # ("text", s) 或 ("code", lang, code)
    pos = 0
    for m in fence.finditer(text):
        if m.start() > pos:
            parts.append(("text", text[pos:m.start()]))
        code = m.group(2)
        if not code.endswith("\n"):
            code += "\n"
        parts.append(("code", m.group(1) or "", code))
        pos = m.end()
    if pos < len(text):
        parts.append(("text", text[pos:]))

    def _fmt_text(seg: str) -> str:
        seg = re.sub(
            r"`([^`]+)`",
            r'<code style="background:#374151;padding:2px 6px;border-radius:3px;font-family:Consolas,monospace;font-size:12px;color:#fbbf24;">\1</code>',
            seg,
        )
        seg = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seg)
        seg = re.sub(r"\*(.+?)\*", r"<em>\1</em>", seg)
        seg = re.sub(r"^### (.+)$", r'<h3 style="color:#4e6ef2;margin:8px 0 4px;">\1</h3>', seg, flags=re.MULTILINE)
        seg = re.sub(r"^## (.+)$", r'<h2 style="color:#4e6ef2;margin:10px 0 6px;">\1</h2>', seg, flags=re.MULTILINE)
        seg = re.sub(r"^- (.+)$", r'<li style="margin-left:16px;">\1</li>', seg, flags=re.MULTILINE)
        seg = seg.replace("\n", "<br>")
        return seg

    out = []
    for part in parts:
        if part[0] == "code":
            lang = part[1]
            code = part[2]
            if lang:
                out.append(
                    f'<pre style="background:#0f172a;border:1px solid #1e293b;'
                    f'border-radius:10px;padding:12px;overflow-x:auto;"><code style="color:#e2e8f0;'
                    f'font-family:Consolas,monospace;font-size:12px;white-space:pre;">{code}</code></pre>'
                )
            else:
                out.append(
                    f'<pre style="background:#0f172a;border:1px solid #1e293b;'
                    f'border-radius:10px;padding:12px;overflow-x:auto;"><code style="color:#e2e8f0;'
                    f'font-family:Consolas,monospace;font-size:12px;white-space:pre;">{code}</code></pre>'
                )
        else:
            out.append(_fmt_text(part[1]))

    return f'<div style="line-height:1.7;">{"".join(out)}</div>'


class MessageBubble(QFrame):
    """单条消息气泡"""

    copy_clicked = Signal(str)
    code_run_clicked = Signal(str, str)  # language, code

    def __init__(self, role: str, content: str, msg_type: str = "text",
                 metadata: Optional[dict] = None, translator=None, parent=None):
        super().__init__(parent)
        self.role = role
        self.content = content
        self.msg_type = msg_type
        self.metadata = metadata or {}
        self.tr = translator

        # 供全局主题 QSS 按角色命中样式（MessageBubble[role="user"/"assistant"]）
        self.setProperty("role", role)
        self._run_button_rows: list = []
        self._run_blocks_sig = None
        self._content_layout = None

        self._init_ui()

    # ---------- 界面 ----------
    def _init_ui(self):
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)
        layout.setAlignment(layout.alignment())

        # 头部：助手带头像+名字+复制；用户右侧仅复制（主题统一着色）
        header = QHBoxLayout()
        header.setSpacing(8)
        if self.role == "assistant":
            avatar = QLabel("✦")
            avatar.setObjectName("avatar")
            avatar.setFixedSize(28, 28)
            avatar.setAlignment(Qt.AlignCenter)
            header.addWidget(avatar)

            who = QLabel("CodeAgent")
            who.setObjectName("who")
            header.addWidget(who)
            header.addStretch()

        copy_btn = QPushButton("复制")
        copy_btn.setObjectName("miniBtn")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(lambda: self.copy_clicked.emit(self.content))
        if self.role == "user":
            header.addStretch()
        header.addWidget(copy_btn)
        layout.addLayout(header)

        # 内容区
        if self.msg_type == "diff":
            self._init_diff_content(layout)
        elif self.msg_type == "error":
            self._init_error_content(layout)
        else:
            self._init_text_content(layout)

    def _init_text_content(self, layout):
        """文本内容（Markdown 渲染 + 代码块运行按钮）"""
        browser = QTextBrowser()
        browser.setObjectName("body")
        browser.setOpenExternalLinks(True)
        browser.setFrameShape(QFrame.NoFrame)
        browser.setMinimumHeight(40)
        browser.setHtml(self._render_markdown(self.content))
        browser.document().contentsChanged.connect(self._adjust_height)
        layout.addWidget(browser)
        self._browser = browser
        self._content_layout = layout
        self._sync_run_buttons()

    def _sync_run_buttons(self):
        """按当前内容同步代码块“运行”按钮（流式更新内容完整后才出现）"""
        layout = self._content_layout
        if layout is None:
            return
        code_blocks = self._extract_code_blocks(self.content)
        sig = tuple((lang, code) for lang, code in code_blocks)
        if sig == self._run_blocks_sig:
            return
        self._run_blocks_sig = sig

        # 移除旧的运行按钮行
        for row in self._run_button_rows:
            while row.count():
                item = row.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            layout.removeItem(row)
        self._run_button_rows = []

        for lang, code in code_blocks:
            if not lang or lang == "text":
                continue
            btn_row = QHBoxLayout()
            run_btn = QPushButton("▶ 运行")
            run_btn.setObjectName("runBtn")
            run_btn.setFixedHeight(26)
            run_btn.setCursor(Qt.PointingHandCursor)
            run_btn.clicked.connect(lambda checked, l=lang, c=code: self.code_run_clicked.emit(l, c))
            btn_row.addWidget(run_btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)
            self._run_button_rows.append(btn_row)

    def _init_diff_content(self, layout):
        """Diff 内容"""
        from ui.chat.diff_viewer import DiffViewer
        old_text = self.metadata.get("old_text", "")
        new_text = self.metadata.get("new_text", "")
        file_path = self.metadata.get("file_path", "")
        viewer = DiffViewer(old_text, new_text, file_path, self.tr)
        layout.addWidget(viewer)

    def _init_error_content(self, layout):
        """错误内容"""
        error_label = QLabel()
        error_label.setObjectName("errorText")
        error_label.setText(f"⚠ {self.content}")
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #ef4444; font-size: 13px;")
        layout.addWidget(error_label)

    def _adjust_height(self):
        """自动调整文本浏览器高度"""
        if hasattr(self, '_browser'):
            doc_height = self._browser.document().size().height()
            self._browser.setMinimumHeight(int(doc_height) + 16)

    def _render_markdown(self, text: str) -> str:
        return render_markdown(text)

    def _extract_code_blocks(self, text: str):
        """提取代码块"""
        blocks = []
        pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        for match in pattern.finditer(text):
            lang = match.group(1) or "text"
            code = match.group(2)
            blocks.append((lang, code))
        return blocks

    def update_content(self, content: str):
        """更新内容（流式输出时用）"""
        self.content = content
        if hasattr(self, '_browser'):
            self._browser.setHtml(self._render_markdown(content))
        self._sync_run_buttons()
