"""开发者工具面板 - 操作日志、API请求、错误堆栈、日志导出"""
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QTextEdit, QHeaderView,
    QComboBox, QLineEdit, QFileDialog, QMessageBox,
)
from PySide6.QtGui import QFont, QColor


class DevToolsPanel(QWidget):
    """开发者工具面板"""

    def __init__(self, database, translator, parent=None):
        super().__init__(parent)
        self.db = database
        self.tr = translator
        self._init_ui()
        self._refresh_logs()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 工具栏
        toolbar = QHBoxLayout()

        self.action_filter = QComboBox()
        # 过滤项与真实记录的 action 保持一致（error 代表失败的记录）
        self.action_filter.addItems([
            self.tr.tr("全部操作"), "agent_chat", self.tr.tr("错误"),
        ])
        self.action_filter.setFixedHeight(28)
        self.action_filter
        self.action_filter.currentIndexChanged.connect(self._refresh_logs)
        toolbar.addWidget(self.action_filter)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索日志...")
        self.search_edit.setFixedHeight(28)
        self.search_edit.setFixedWidth(200)
        self.search_edit
        self.search_edit.textChanged.connect(self._refresh_logs)
        toolbar.addWidget(self.search_edit)

        toolbar.addStretch()

        btn_refresh = QPushButton("🔄 刷新")
        btn_refresh.setFixedHeight(28)
        btn_refresh.setStyleSheet(self._btn_style())
        btn_refresh.clicked.connect(self._refresh_logs)
        toolbar.addWidget(btn_refresh)

        btn_export = QPushButton("📥 导出日志")
        btn_export.setFixedHeight(28)
        btn_export.setStyleSheet(self._btn_style())
        btn_export.clicked.connect(self._export_logs)
        toolbar.addWidget(btn_export)

        btn_clear = QPushButton("🗑 清空日志")
        btn_clear.setFixedHeight(28)
        btn_clear.setStyleSheet(self._btn_style("#ef4444"))
        btn_clear.clicked.connect(self._clear_logs)
        toolbar.addWidget(btn_clear)

        layout.addLayout(toolbar)

        # Tab
        self.tabs = QTabWidget()
        self.tabs

        # 操作日志表格
        self.log_table = QTableWidget()
        self.log_table.setColumnCount(5)
        self.log_table.setHorizontalHeaderLabels([
            self.tr.tr("时间"), self.tr.tr("操作"), self.tr.tr("详情"),
            self.tr.tr("状态"), self.tr.tr("耗时"),
        ])
        self.log_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.log_table
        self.log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabs.addTab(self.log_table, "📋 " + self.tr.tr("操作日志"))

        # API 请求日志
        self.api_log = QTextEdit()
        self.api_log.setReadOnly(True)
        self.api_log.setFont(QFont("Consolas", 10))
        self.api_log
        self.tabs.addTab(self.api_log, "🔌 API 请求")

        # 错误堆栈
        self.error_log = QTextEdit()
        self.error_log.setReadOnly(True)
        self.error_log.setFont(QFont("Consolas", 10))
        self.error_log
        self.tabs.addTab(self.error_log, "❌ 错误堆栈")

        layout.addWidget(self.tabs, 1)

        # 状态栏
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self.status_label)

    def _btn_style(self, color="#6366f1") -> str:
        return f"""
            QPushButton {{ background: {color}; color: white; border: none;
                          border-radius: 4px; padding: 0 12px; font-size: 12px; }}
            QPushButton:hover {{ background: {color}; opacity: 0.8; }}
        """

    def _refresh_logs(self):
        action = self.action_filter.currentText()
        if action == self.tr.tr("全部操作"):
            action = ""
        filter_failed = (action == self.tr.tr("错误"))
        if filter_failed:
            action = ""
        keyword = self.search_edit.text().strip()

        logs = self.db.list_logs(limit=500, action=action)
        if filter_failed:
            logs = [l for l in logs if l.get("status") == "failed"]
        if keyword:
            logs = [l for l in logs if keyword in (l.get("detail", "") + l.get("action", ""))]

        self.log_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            # 时间
            ts = log.get("created_at", 0)
            time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
            item = QTableWidgetItem(time_str)
            item.setForeground(QColor("#9ca3af"))
            self.log_table.setItem(row, 0, item)

            # 操作
            item = QTableWidgetItem(log.get("action", ""))
            item.setForeground(QColor("#a78bfa"))
            self.log_table.setItem(row, 1, item)

            # 详情
            detail = log.get("detail", "")
            if len(detail) > 100:
                detail = detail[:100] + "..."
            item = QTableWidgetItem(detail)
            self.log_table.setItem(row, 2, item)

            # 状态
            status = log.get("status", "success")
            item = QTableWidgetItem(status)
            if status == "success":
                item.setForeground(QColor("#34d399"))
            else:
                item.setForeground(QColor("#f87171"))
            self.log_table.setItem(row, 3, item)

            # 耗时
            duration = log.get("duration", 0)
            item = QTableWidgetItem(f"{duration:.2f}s" if duration else "")
            item.setForeground(QColor("#fbbf24"))
            self.log_table.setItem(row, 4, item)

        self.status_label.setText(f"{len(logs)} 条日志")

        # 错误日志
        errors = [l for l in logs if l.get("status") == "failed"]
        error_text = ""
        for e in errors:
            error_text += f"[{datetime.fromtimestamp(e.get('created_at', 0)).strftime('%Y-%m-%d %H:%M:%S')}] "
            error_text += f"{e.get('action', '')}: {e.get('detail', '')}\n\n"
        self.error_log.setPlainText(error_text or "暂无错误")

    def _export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr.tr("导出日志"), "codeagent_logs.json",
            "JSON (*.json);;CSV (*.csv);;文本 (*.txt)"
        )
        if not path:
            return
        logs = self.db.list_logs(limit=10000)
        try:
            if path.endswith(".json"):
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(logs, f, ensure_ascii=False, indent=2)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    for log in logs:
                        ts = datetime.fromtimestamp(log.get("created_at", 0)).strftime("%Y-%m-%d %H:%M:%S")
                        f.write(f"[{ts}] {log.get('action','')} | {log.get('status','')} | {log.get('detail','')}\n")
            QMessageBox.information(self, self.tr.tr("导出"), f"{self.tr.tr('日志已导出到')}: {path}")
        except Exception as e:
            QMessageBox.warning(self, self.tr.tr("错误"), str(e))

    def _clear_logs(self):
        reply = QMessageBox.question(
            self, self.tr.tr("清空日志"),
            self.tr.tr("确定清空所有操作日志吗？此操作不可撤销。"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            # 清空日志表
            self.db._connect().execute("DELETE FROM action_logs")
            self.db._connect().commit()
            self._refresh_logs()
