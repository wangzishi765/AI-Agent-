"""
对话主面板 - 整合消息列表、输入框，处理 Agent 交互
支持流式输出、工具调用展示、文件附件、语音输入
"""
import threading
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QFrame, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, Signal, QTimer

from core.agent import CodeAgent, AgentTask, strip_protocol_markers
from app.constants import ROLE_USER, ROLE_ASSISTANT

from ui.chat.message_bubble import MessageBubble
from ui.chat.input_box import InputBox


class ChatWidget(QWidget):
    """对话主面板"""

    task_started = Signal(object)
    task_finished = Signal(object)
    conversation_created = Signal(int)
    text_inserted = Signal(str)

    # 内部信号：后台 Agent 线程只能通过这些信号把 UI 更新投递回 GUI 线程
    # （QTimer.singleShot 在无事件循环的 Python 线程中永远不会触发）
    _sig_bubble = Signal(str, str, str, object)   # role, content, msg_type, metadata
    _sig_stream_start = Signal(str)               # 创建流式占位气泡（GUI 线程持有指针）
    _sig_bubble_update = Signal(str)              # 流式更新当前气泡内容
    _sig_processing_done = Signal()
    _sig_voice_result = Signal(str)
    _sig_ask_permission = Signal(str, str, object, object)  # action, detail, holder, event
    _sig_diff = Signal(str, str, str)  # path, old_text, new_text

    def __init__(self, config, db, agent: CodeAgent, translator,
                 ocr_engine=None, speech_recognizer=None, file_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = db
        self.agent = agent
        self.tr = translator
        self.ocr_engine = ocr_engine
        self.speech_recognizer = speech_recognizer
        self.file_manager = file_manager

        self.current_conversation_id: Optional[int] = None
        self.current_project: str = ""
        self._is_processing = False
        self._current_bubble: Optional[MessageBubble] = None
        self._stream_buffer = ""

        # 内部信号连接到 GUI 线程槽
        self._sig_bubble.connect(self._add_message_bubble)
        self._sig_stream_start.connect(self._start_stream_bubble)
        self._sig_bubble_update.connect(self._update_current_bubble)
        self._sig_processing_done.connect(self._on_processing_done)
        self._sig_voice_result.connect(self._insert_voice_text)
        self._sig_ask_permission.connect(self._ask_permission_dialog)
        self._sig_diff.connect(self._add_diff_bubble)

        # 设置 Agent 回调
        self.agent.on_token = self._on_token
        self.agent.on_stream_turn = self._on_agent_stream_turn
        self.agent.on_tool_call = self._on_tool_call
        self.agent.on_tool_result = self._on_tool_result
        self.agent.on_task_start = self._on_task_start
        self.agent.on_task_end = self._on_task_end
        self.agent.on_permission_check = self._on_permission_check
        self.agent.on_file_changed = self._on_file_changed

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 欢迎页（无对话时显示）
        self.welcome_widget = self._create_welcome_widget()
        layout.addWidget(self.welcome_widget)

        # 消息滚动区（放进与输入框同一边距的容器，随窗口同步伸缩）
        self.scroll_host = QWidget()
        self.scroll_host.setObjectName("scrollHost")
        self.scroll_host_layout = QHBoxLayout(self.scroll_host)
        self.scroll_host_layout.setContentsMargins(16, 0, 16, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("chatScroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.messages_container = QWidget()
        self.messages_container.setObjectName("threadColumn")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(4, 18, 4, 12)
        self.messages_layout.setSpacing(14)
        self.messages_layout.addStretch()
        self.scroll_area.setWidget(self.messages_container)
        self.scroll_host_layout.addWidget(self.scroll_area, 1)
        self.scroll_host.hide()
        layout.addWidget(self.scroll_host, 1)

        # 输入区（边距在 resizeEvent 与消息列同步）
        input_host = QWidget()
        input_host.setObjectName("inputHost")
        self.input_row = QHBoxLayout(input_host)
        self.input_row.setContentsMargins(16, 6, 16, 16)
        self.input_box = InputBox(self.tr)
        self.input_box.send_clicked.connect(self._on_send)
        self.input_box.attach_files.connect(self._on_attach_files)
        self.input_box.voice_start.connect(self._on_voice_start)
        self.input_box.voice_stop.connect(self._on_voice_stop)
        if self.config.get("ocr_enabled", True) and self.ocr_engine:
            self.input_box.set_ocr_engine(self.ocr_engine)
        self.input_row.addWidget(self.input_box, 1)
        layout.addWidget(input_host)

    # 消息/输入共用内容列的最大宽度
    MAX_CONTENT_WIDTH = 920

    def resizeEvent(self, event):
        """窗口缩放时，消息列与底部输入框同步限宽并保持居中伸缩"""
        super().resizeEvent(event)
        side = max(12, (self.width() - self.MAX_CONTENT_WIDTH) // 2)
        if hasattr(self, "scroll_host_layout"):
            self.scroll_host_layout.setContentsMargins(side, 0, side, 0)
        if hasattr(self, "messages_layout"):
            self.messages_layout.setContentsMargins(4, 18, 4, 12)
        if hasattr(self, "input_row"):
            self.input_row.setContentsMargins(side, 6, side, 16)

    def _create_welcome_widget(self) -> QWidget:
        """创建欢迎页（居中 logo + 提示卡片）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 40, 40, 60)

        logo = QLabel("⚡")
        logo.setObjectName("welcomeLogo")
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        title = QLabel("CodeAgent")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(self.tr.tr("你的 AI 编程助手，写代码、改代码、调试、审查"))
        subtitle.setObjectName("welcomeSub")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(14)

        # 提示卡片：上中下三个建议
        card = QFrame()
        card.setObjectName("tipCard")
        card.setMaximumWidth(560)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(8)
        tips = [
            ("💡 帮你写", "「帮我写一个 Python 快速排序」"),
            ("🧭 项目分析", "「读取当前项目并分析代码结构」"),
            ("🐛 定位 Bug", "「这个报错怎么修？（粘贴错误信息）」"),
            ("🔨 重构建议", "「重构这个函数，提高可读性」"),
        ]
        for head, tail in tips:
            row = QHBoxLayout()
            head_label = QLabel(head)
            head_label.setObjectName("tipLine")
            head_label.setStyleSheet("font-weight:600; color:#4e6ef2; background:transparent;")
            row.addWidget(head_label)
            tail_label = QLabel(tail)
            tail_label.setObjectName("tipLine")
            row.addWidget(tail_label)
            row.addStretch()
            card_layout.addLayout(row)
        layout.addWidget(card, 0, Qt.AlignCenter)

        return widget

    def set_project(self, path: str):
        self.current_project = path
        self.agent.set_project(path)

    def load_conversation(self, conv_id: int):
        """加载对话历史（Agent 执行中禁止切换，避免线程竞态导致消息归属错乱）"""
        if self._is_processing:
            QMessageBox.information(
                self, self.tr.tr("提示"),
                self.tr.tr("Agent 正在执行任务，请等待完成后再切换对话。"),
            )
            return
        self.current_conversation_id = conv_id
        self.agent.set_conversation(conv_id)

        # 清空消息
        self._clear_messages()

        # 加载历史
        messages = self.db.list_messages(conv_id)
        if messages:
            self.welcome_widget.hide()
            self.scroll_host.show()
            for msg in messages:
                if msg.get("msg_type") == "tool_result":
                    continue  # 跳过工具结果消息
                self._add_message_bubble(
                    msg["role"], msg["content"],
                    msg_type=msg.get("msg_type", "text"),
                    metadata=msg.get("metadata", {}),
                )
        else:
            self.welcome_widget.show()
            self.scroll_host.hide()

    def _clear_messages(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _add_message_bubble(self, role: str, content: str,
                             msg_type: str = "text", metadata: dict = None):
        """添加消息气泡（用户靠右 / 助手靠左；展示层统一剥离协议标记）"""
        if content and "<<<" in content:
            content = strip_protocol_markers(content)
        bubble = MessageBubble(role, content, msg_type, metadata or {}, self.tr)
        bubble.setMaximumWidth(900)
        bubble.copy_clicked.connect(self._copy_text)
        bubble.code_run_clicked.connect(self._run_code)
        align = Qt.AlignRight if role == ROLE_USER else Qt.AlignLeft
        # 插入到 stretch 之前
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, bubble, 0, align)
        QApplication.processEvents()
        self._scroll_to_bottom()
        return bubble

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        ))

    def _copy_text(self, text: str):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _run_code(self, language: str, code: str):
        """运行代码（在后台线程执行，结果经信号回投，避免冻结 GUI）"""
        config = self.config

        def worker():
            from core.code_executor import CodeExecutor
            executor = CodeExecutor(config)
            result = executor.run_code(language, code)
            # 在对话中显示结果
            output = f"退出码: {result['exit_code']}\n耗时: {result['duration']}s\n\n"
            if result.get("stdout"):
                output += f"标准输出:\n{result['stdout']}\n"
            if result.get("stderr"):
                output += f"错误输出:\n{result['stderr']}\n"
            self._sig_bubble.emit(ROLE_ASSISTANT, output, "terminal", {})

        threading.Thread(target=worker, daemon=True).start()

    # ============ 发送消息 ============
    def _on_send(self, text: str):
        if self._is_processing:
            # Agent 正在执行：输入框已被清空，把文字还回去避免用户消息丢失
            if text:
                self.input_box.insert_text(text)
            return

        # 附加文件内容
        attached_files = self.input_box.get_attached_files()
        full_text = text
        if attached_files and self.file_manager:
            file_contents = []
            for path in attached_files:
                try:
                    content = self.file_manager.read_file(path)
                    file_contents.append(f"文件: {path}\n```\n{content}\n```")
                except Exception as e:
                    file_contents.append(f"文件: {path} (读取失败: {e})")
            if file_contents:
                full_text = text + "\n\n" + "\n\n".join(file_contents)

        if not full_text.strip():
            return

        # 确保有对话
        if not self.current_conversation_id:
            self._create_conversation()

        self.welcome_widget.hide()
        self.scroll_host.show()

        # 添加用户消息
        self._add_message_bubble(ROLE_USER, text)

        # 异步执行 Agent
        self._is_processing = True
        self.input_box.btn_send.setEnabled(False)
        self.input_box.btn_send.setText("思考中...")

        thread = threading.Thread(target=self._run_agent, args=(full_text,), daemon=True)
        thread.start()

    def _create_conversation(self):
        title = self.tr.tr("新对话")
        project_id = None
        if self.current_project:
            for p in self.db.list_projects():
                if p["path"] == self.current_project:
                    project_id = p["id"]
                    break
        conv_id = self.db.create_conversation(
            project_id=project_id, title=title,
            model=self.config.get("active_model", "deepseek"),
        )
        self.current_conversation_id = conv_id
        self.agent.set_conversation(conv_id)
        self.conversation_created.emit(conv_id)

    def _run_agent(self, text: str):
        """在后台线程运行 Agent（所有 UI 更新通过 _sig_* 信号投递回 GUI 线程）"""
        try:
            self._stream_buffer = ""
            self._sig_stream_start.emit("思考中...")
            self.agent.chat(text)
        except Exception as e:
            error_msg = f"执行出错: {str(e)}"
            self._sig_bubble.emit(ROLE_ASSISTANT, error_msg, "error", {})
        finally:
            self._sig_processing_done.emit()

    def _start_stream_bubble(self, placeholder: str):
        """GUI 线程：创建助手占位气泡并记录指针，供流式更新使用。

        注意：必须先把 self._current_bubble 指向新气泡，再调用会触发
        嵌套 processEvents 的代码，否则快速流式输出会在指针赋值前被
        排空并丢失（表现为气泡停留在“思考中...”）。
        """
        bubble = MessageBubble(ROLE_ASSISTANT, placeholder, "text", {}, self.tr)
        bubble.setMaximumWidth(900)
        bubble.copy_clicked.connect(self._copy_text)
        bubble.code_run_clicked.connect(self._run_code)
        self.messages_layout.insertWidget(
            self.messages_layout.count() - 1, bubble, 0, Qt.AlignLeft
        )
        self._current_bubble = bubble
        QApplication.processEvents()
        self._scroll_to_bottom()

    def _on_agent_stream_turn(self):
        """Agent 工作线程：新一轮模型输出开始——清空缓冲并另开新气泡"""
        self._stream_buffer = ""
        self._sig_stream_start.emit("思考中...")

    def _on_token(self, token: str):
        """流式输出回调（在 Agent 后台线程调用，经信号转到 UI 线程）"""
        self._stream_buffer += token
        self._sig_bubble_update.emit(self._stream_buffer)

    def _update_current_bubble(self, content: str):
        """GUI 线程：更新当前流式气泡内容（展示层剥离协议标记，防御已删除控件）"""
        if self._current_bubble is None:
            return
        if "<<<" in content:
            content = strip_protocol_markers(content)
        try:
            self._current_bubble.update_content(content)
        except RuntimeError:
            # 气泡已被销毁（如切换对话），放弃本次更新
            self._current_bubble = None

    def _on_tool_call(self, name: str, params: dict):
        """工具调用回调"""
        tool_msg = f"🔧 调用工具: {name}\n参数: {params}"
        self._sig_bubble.emit(
            ROLE_ASSISTANT, tool_msg, "text",
            {"tool_call": True, "tool_name": name},
        )

    def _on_tool_result(self, name: str, result):
        """工具结果回调"""
        result_str = str(result)
        if len(result_str) > 2000:
            result_str = result_str[:2000] + "\n... (已截断) ..."
        tool_msg = f"✅ 工具 {name} 执行结果:\n```\n{result_str}\n```"
        self._sig_bubble.emit(
            ROLE_ASSISTANT, tool_msg, "text",
            {"tool_result": True, "tool_name": name},
        )

    def _on_file_changed(self, path: str, old_text: str, new_text: str):
        """Agent 工作线程回调：文件变更后转发给 GUI 显示 Diff"""
        self._sig_diff.emit(path, old_text, new_text)

    def _add_diff_bubble(self, path: str, old_text: str, new_text: str):
        """GUI 线程：追加一条 Diff 对比气泡"""
        # 大文件不整段渲染，只提示
        if len(old_text) > 200_000 or len(new_text) > 200_000:
            self._sig_bubble.emit(
                ROLE_ASSISTANT, f"📝 文件已修改: {path}", "text", {}
            )
            return
        self._sig_bubble.emit(
            ROLE_ASSISTANT, "", "diff",
            {"file_path": path, "old_text": old_text, "new_text": new_text},
        )

    def _on_task_start(self, task: AgentTask):
        self.task_started.emit(task)

    def _on_task_end(self, task: AgentTask):
        self.task_finished.emit(task)

    def _on_processing_done(self):
        self._is_processing = False
        self._current_bubble = None
        self.input_box.btn_send.setEnabled(True)
        self.input_box.btn_send.setText("发送 ➤")

    # ============ 权限确认（strict / semiauto） ============
    def _on_permission_check(self, action: str, params: dict) -> bool:
        """由 Agent 后台线程调用：把确认请求投递到 GUI 线程并阻塞等待用户决定"""
        event = threading.Event()
        holder = {"result": False}
        detail = str(params.get("path") or params.get("message") or "")
        self._sig_ask_permission.emit(action, detail, holder, event)
        if not event.wait(300):  # 5 分钟未响应视为拒绝，避免永久卡死
            holder["result"] = False
        return holder["result"]

    def _ask_permission_dialog(self, action: str, detail: str, holder: dict, event):
        """GUI 线程：弹出确认对话框并回写结果"""
        try:
            if action in ("write_file", "edit_file"):
                prompt = self.tr.tr("允许文件写入/修改操作吗？")
            elif action == "git_commit":
                prompt = self.tr.tr("允许执行 Git 提交吗？")
            else:
                prompt = f"{self.tr.tr('允许执行以下操作吗？')}\n{action}"
            if detail:
                prompt += f"\n\n{detail}"
            reply = QMessageBox.question(
                self, self.tr.tr("权限确认"), prompt,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            holder["result"] = (reply == QMessageBox.Yes)
        except Exception:
            holder["result"] = False
        finally:
            event.set()

    # ============ 附件 ============
    def _on_attach_files(self, files: list):
        pass  # 文件在发送时处理

    def attach_file(self, path: str):
        """从外部附加文件"""
        self.input_box._add_attachment(path)

    # ============ 语音 ============
    def _on_voice_start(self):
        if not self.speech_recognizer or not self.speech_recognizer.is_available():
            QMessageBox.warning(self, "语音输入", "语音识别不可用，请安装 PyAudio 和 SpeechRecognition")
            return

        def on_result(text):
            if text:
                # 语音识别线程中不得直接操作 GUI，通过信号转回主线程
                self._sig_voice_result.emit(text)

        def on_error(err):
            pass

        self.speech_recognizer.start_listening(on_result, on_error,
                                                 language=self.config.get("voice_language", "zh-CN"))

    def _insert_voice_text(self, text: str):
        """GUI 线程：把语音识别结果插入输入框"""
        if text:
            self.input_box.insert_text(text + " ")

    def _on_voice_stop(self):
        if self.speech_recognizer:
            self.speech_recognizer.stop_listening()

    def insert_text(self, text: str):
        """插入文本到输入框"""
        self.input_box.insert_text(text)
        self.text_inserted.emit(text)
