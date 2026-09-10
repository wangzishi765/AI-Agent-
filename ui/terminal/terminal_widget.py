"""
终端组件 - 支持多标签、命令输入、输出显示
基于 QProcess 实现真实终端交互
"""
import os
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import Qt, Signal, QProcess
from PySide6.QtGui import QFont, QTextCursor


class TerminalTab(QWidget):
    """单个终端标签页"""

    title_changed = Signal(str)

    def __init__(self, working_dir: str = "", translator=None, parent=None):
        super().__init__(parent)
        self.tr = translator
        self.working_dir = working_dir or os.path.expanduser("~")
        self.process: Optional[QProcess] = None
        self._init_ui()
        self._start_shell()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 输出区
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 11))
        self.output.setStyleSheet("""
            QTextEdit { background: #0d1117; color: #e6edf3; border: none;
                        padding: 8px; font-size: 12px; }
        """)
        layout.addWidget(self.output, 1)

        # 输入行
        input_bar = QFrame()
        input_bar.setStyleSheet("background: #0d1117; border-top: 1px solid #30363d;")
        input_layout = QHBoxLayout(input_bar)
        input_layout.setContentsMargins(8, 4, 8, 4)

        self.prompt_label = QLabel("❯")
        self.prompt_label.setStyleSheet("color: #34d399; font-weight: bold;")
        input_layout.addWidget(self.prompt_label)

        self.input_edit = QLineEdit()
        self.input_edit.setFont(QFont("Consolas", 11))
        self.input_edit.setStyleSheet("""
            QLineEdit { background: transparent; color: #e6edf3; border: none;
                        padding: 2px; font-size: 12px; }
        """)
        self.input_edit.returnPressed.connect(self._execute_command)
        input_layout.addWidget(self.input_edit, 1)

        layout.addWidget(input_bar)

    def _start_shell(self):
        """启动 shell 进程"""
        self.process = QProcess(self)
        self.process.setWorkingDirectory(self.working_dir)

        # Windows 使用 cmd，Linux/Mac 使用 bash
        if os.name == "nt":
            self.process.setProgram("cmd.exe")
            self.process.setArguments(["/k", "chcp 65001 >nul"])
        else:
            self.process.setProgram("/bin/bash")
            self.process.setArguments(["--login"])

        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

        self.process.start()
        self.process.waitForStarted(1000)

    def _on_stdout(self):
        data = self.process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._append_output(data)

    def _on_stderr(self):
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._append_output(data, error=True)

    def _on_finished(self, exit_code, exit_status):
        self._append_output(f"\n[进程已退出，退出码: {exit_code}]\n", error=True)

    def _append_output(self, text: str, error: bool = False):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        if error:
            import html
            cursor.insertHtml(f'<span style="color:#f87171;">{html.escape(text)}</span>')
        else:
            cursor.insertText(text)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def _execute_command(self):
        command = self.input_edit.text().strip()
        if not command:
            return

        self._append_output(f"\n❯ {command}\n")
        self.input_edit.clear()

        if self.process and self.process.state() == QProcess.Running:
            self.process.write((command + "\n").encode("utf-8"))
        else:
            # 进程已退出，用临时方式执行
            from PySide6.QtCore import QProcess
            QProcess.execute("cmd.exe", ["/c", command]) if os.name == "nt" else QProcess.execute("bash", ["-c", command])

    def run_command(self, command: str):
        """外部调用：在终端中执行命令"""
        self.input_edit.setText(command)
        self._execute_command()

    def set_working_dir(self, path: str):
        self.working_dir = path
        if self.process:
            self.process.setWorkingDirectory(path)

    def clear(self):
        self.output.clear()

    def closeEvent(self, event):
        if self.process:
            self.process.kill()
        super().closeEvent(event)


class TerminalWidget(QWidget):
    """终端组件（多标签）"""

    def __init__(self, config, translator, parent=None):
        super().__init__(parent)
        self.config = config
        self.tr = translator
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标签栏
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { border: none; background: #0d1117; }
            QTabBar::tab { background: #161b22; color: #9ca3af; padding: 4px 16px;
                           border: none; font-size: 11px; }
            QTabBar::tab:selected { background: #0d1117; color: #e6edf3; }
            QTabBar::tab-close { image: none; }
        """)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)

        # 新建标签按钮
        btn_new = QPushButton("+")
        btn_new.setFixedSize(28, 28)
        btn_new.setStyleSheet("""
            QPushButton { background: transparent; color: #9ca3af; border: none;
                          font-size: 16px; font-weight: bold; }
            QPushButton:hover { color: #e6edf3; }
        """)
        btn_new.clicked.connect(lambda: self.add_tab())
        self.tab_widget.setCornerWidget(btn_new, Qt.TopRightCorner)

        layout.addWidget(self.tab_widget)

        # 默认新建一个标签
        self.add_tab()

    def add_tab(self, working_dir: str = "") -> TerminalTab:
        tab = TerminalTab(working_dir, self.tr)
        index = self.tab_widget.addTab(tab, f"终端 {self.tab_widget.count() + 1}")
        self.tab_widget.setCurrentIndex(index)
        return tab

    def _close_tab(self, index):
        if self.tab_widget.count() <= 1:
            return
        widget = self.tab_widget.widget(index)
        if widget:
            widget.deleteLater()
        self.tab_widget.removeTab(index)

    def run_command(self, command: str, working_dir: str = ""):
        """在当前终端执行命令"""
        tab = self.tab_widget.currentWidget()
        if tab:
            if working_dir:
                tab.set_working_dir(working_dir)
            tab.run_command(command)

    def clear_current(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            tab.clear()
