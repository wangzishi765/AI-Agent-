"""
CodeAgent 核心大脑
负责：理解用户意图、规划任务、调用工具（读/写/运行/Git）、生成结果
采用基于指令标记的工具调用协议，兼容所有 OpenAI 兼容模型
"""
import os
import re
import json
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from models.base import BaseModel, ChatMessage
from app.constants import (
    ROLE_USER, ROLE_ASSISTANT, ROLE_SYSTEM,
    PERMISSION_STRICT, PERMISSION_SEMIAUTO, PERMISSION_FULL,
    TASK_RUNNING, TASK_SUCCESS, TASK_FAILED,
)


# ============ 工具调用协议 ============
# 模型输出中使用 <<<TOOL:name>>> ... <<<END>>> 标记工具调用
TOOL_PATTERN = re.compile(r"<<<TOOL:(\w+)>>>(.*?)<<<END>>>", re.DOTALL)

# 用于把“含协议标记的原始内容”清洗成面向用户的可读文本
_PROTOCOL_TEXT_PATTERN = re.compile(
    r"<<<TOOL:.*?<<<END>>>|<<<RESULT:.*?<<<END_RESULT>>>", re.DOTALL
)


def strip_protocol_markers(text: str) -> str:
    """移除 <<<TOOL/<<<RESULT 协议块（流式展示、历史回显、导出共用）"""
    if not text:
        return text
    return _PROTOCOL_TEXT_PATTERN.sub("", text).strip("\n")


SYSTEM_PROMPT = """你是 CodeAgent，一个专业的代码 AI 助手，专注于帮助用户完成所有代码相关任务。

## 你的能力
你可以通过工具调用直接操作用户的电脑：
- 读取文件、写入文件、修改文件
- 在 Docker 容器中运行代码和命令
- 执行 Git 操作（提交、分支、diff）
- 搜索文件和代码内容
- 格式化代码、运行 Linter

## 工具调用格式
当你需要执行操作时，在回复中使用以下格式（必须严格遵守）：

<<<TOOL:工具名>>>
{"参数名": "参数值"}
<<<END>>>

## 可用工具

### read_file - 读取文件内容
参数: {"path": "文件绝对路径或相对项目路径"}

### write_file - 写入/创建文件
参数: {"path": "文件路径", "content": "文件内容"}

### edit_file - 编辑文件（替换指定文本）
参数: {"path": "文件路径", "old_text": "要替换的原文", "new_text": "新文本"}

### run_code - 在 Docker 容器中运行代码/命令
参数: {"language": "python/bash/javascript/...", "code": "要运行的代码", "timeout": 300}

### run_command - 在项目目录运行 shell 命令
参数: {"command": "命令字符串", "timeout": 300}

### git_status - 查看 Git 状态
参数: {}

### git_diff - 查看变更 diff
参数: {"path": "可选，指定文件"}

### git_commit - 提交更改
参数: {"message": "提交信息"}

### git_branch - 查看/切换分支
参数: {"action": "list|switch|create", "name": "分支名（switch/create时需要）"}

### search_files - 按文件名搜索
参数: {"pattern": "搜索关键词", "limit": 50}

### search_code - 全局搜索代码内容
参数: {"query": "搜索内容", "limit": 50}

### list_dir - 列出目录内容
参数: {"path": "目录路径"}

## 工作原则
1. **先理解，后动手**：先分析用户需求，必要时读取相关文件了解上下文
2. **小步迭代**：复杂任务拆成小步骤，每步验证
3. **透明操作**：每次工具调用后，用自然语言说明你做了什么、结果如何
4. **代码质量**：生成的代码要规范、有注释、符合最佳实践
5. **错误处理**：运行出错时，分析错误原因并修复，而不是直接放弃
6. **不要编造**：不确定的内容要说明，不要瞎编文件内容或运行结果

## 回复格式
- 普通解释用自然语言
- 代码用 markdown 代码块，并标注语言
- 工具调用必须用 <<<TOOL:...>>> 格式，不要放在代码块里
- 工具调用结果会以 <<<RESULT:...>>> 形式返回给你，根据结果继续下一步

现在开始，用专业、高效的方式帮助用户完成代码任务。"""


@dataclass
class AgentTask:
    """Agent 任务状态"""
    id: str = ""
    status: str = TASK_RUNNING
    start_time: float = field(default_factory=time.time)
    end_time: float = 0
    result: str = ""
    error: str = ""
    tool_calls: List[Dict] = field(default_factory=list)

    @property
    def duration(self) -> float:
        end = self.end_time or time.time()
        return round(end - self.start_time, 2)


class CodeAgent:
    """代码 Agent 核心"""

    def __init__(self, model: BaseModel, config, database,
                 file_manager=None, code_executor=None, git_manager=None,
                 search_engine=None, formatter=None):
        self.model = model
        self.config = config
        self.db = database
        self.file_manager = file_manager
        self.code_executor = code_executor
        self.git_manager = git_manager
        self.search_engine = search_engine
        self.formatter = formatter

        self.project_root: str = ""
        self.conversation_id: Optional[int] = None
        self._messages: List[ChatMessage] = []
        self._current_task: Optional[AgentTask] = None

        # 事件回调
        self.on_token: Optional[Callable[[str], None]] = None
        self.on_stream_turn: Optional[Callable[[], None]] = None  # 新一轮模型输出开始前回调（工作线程）
        self.on_tool_call: Optional[Callable[[str, Dict], None]] = None
        self.on_tool_result: Optional[Callable[[str, Any], None]] = None
        self.on_message: Optional[Callable[[str, str], None]] = None  # role, content
        self.on_task_start: Optional[Callable[[AgentTask], None]] = None
        self.on_task_end: Optional[Callable[[AgentTask], None]] = None
        self.on_permission_check: Optional[Callable[[str, Dict], bool]] = None
        # 文件被写入/编辑后回调 (path, old_text, new_text)，用于 Diff 预览
        self.on_file_changed: Optional[Callable[[str, str, str], None]] = None

    def set_project(self, project_root: str):
        self.project_root = project_root

    def set_conversation(self, conv_id: int):
        self.conversation_id = conv_id
        # 加载历史消息（跳过工具结果，以及含原始工具调用协议的助手消息，
        # 避免“孤儿工具调用”或协议原文被回灌给模型）
        self._messages = []
        if conv_id:
            history = self.db.list_messages(conv_id)
            for msg in history:
                if msg.get("msg_type") == "tool_result":
                    continue
                content = msg.get("content", "") or ""
                if msg.get("role") == ROLE_ASSISTANT and TOOL_PATTERN.search(content):
                    continue
                self._messages.append(ChatMessage(
                    role=msg["role"],
                    content=content,
                ))

    def _resolve_path(self, path: str) -> str:
        """将相对路径解析为绝对路径"""
        if os.path.isabs(path):
            return path
        if self.project_root:
            return os.path.join(self.project_root, path)
        return os.path.abspath(path)

    def _capture_old_content(self, path: str) -> str:
        """写文件前读取旧内容（用于 Diff 预览），失败返回空串"""
        try:
            return self.file_manager.read_file(path) if self.file_manager else ""
        except Exception:
            return ""

    def _notify_file_changed(self, path: str, old_content: str):
        """文件变更后回调（path, old, new），仅在开启 Diff 预览且内容确实变化时触发"""
        if not self.on_file_changed:
            return
        if not self.config.get("show_diff_preview", True):
            return
        # 大文件不整读整传，仅通知“文件已修改”
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if len(old_content) > 200_000 or size > 200_000:
            try:
                self.on_file_changed(path, "", "")
            except Exception:
                pass
            return
        try:
            new_content = self.file_manager.read_file(path) if self.file_manager else ""
        except Exception:
            return
        if new_content != old_content:
            try:
                self.on_file_changed(path, old_content, new_content)
            except Exception:
                pass

    def _check_permission(self, action: str, params: Dict) -> bool:
        """权限检查"""
        mode = self.config.get("permission_mode", PERMISSION_FULL)
        if mode == PERMISSION_FULL:
            return True
        if mode == PERMISSION_SEMIAUTO:
            # 半自动：写文件需要确认，运行代码自动
            if action in ("write_file", "edit_file", "git_commit"):
                if self.on_permission_check:
                    return self.on_permission_check(action, params)
                return True
            return True
        if mode == PERMISSION_STRICT:
            if self.on_permission_check:
                return self.on_permission_check(action, params)
            return True
        return True

    # ============ 工具执行 ============
    def _execute_tool(self, name: str, params: Dict) -> Tuple[str, Any]:
        """执行工具调用，返回 (状态, 结果)"""
        name = name.lower()
        try:
            if name == "read_file":
                path = self._resolve_path(params.get("path", ""))
                content = self.file_manager.read_file(path) if self.file_manager else ""
                return "success", content

            elif name == "write_file":
                path = self._resolve_path(params.get("path", ""))
                content = params.get("content", "")
                if not self._check_permission("write_file", {"path": path}):
                    return "denied", "用户拒绝了写入操作"
                old_content = self._capture_old_content(path)
                if self.file_manager:
                    self.file_manager.write_file(path, content)
                # 自动格式化
                if self.config.get("auto_format", True) and self.formatter:
                    self.formatter.format_file(path)
                self._notify_file_changed(path, old_content)
                return "success", f"文件已写入: {path}"

            elif name == "edit_file":
                path = self._resolve_path(params.get("path", ""))
                old_text = params.get("old_text", "")
                new_text = params.get("new_text", "")
                if not self._check_permission("edit_file", {"path": path}):
                    return "denied", "用户拒绝了编辑操作"
                old_content = self._capture_old_content(path)
                if self.file_manager:
                    self.file_manager.edit_file(path, old_text, new_text)
                if self.config.get("auto_format", True) and self.formatter:
                    self.formatter.format_file(path)
                self._notify_file_changed(path, old_content)
                return "success", f"文件已编辑: {path}"

            elif name == "run_code":
                language = params.get("language", "python")
                code = params.get("code", "")
                timeout = params.get("timeout", 300)
                if self.code_executor:
                    result = self.code_executor.run_code(language, code, timeout)
                    return "success", result
                return "error", "代码执行器未初始化"

            elif name == "run_command":
                command = params.get("command", "")
                timeout = params.get("timeout", 300)
                if self.code_executor:
                    result = self.code_executor.run_command(command, self.project_root, timeout)
                    return "success", result
                return "error", "命令执行器未初始化"

            elif name == "git_status":
                if self.git_manager:
                    return "success", self.git_manager.status(self.project_root)
                return "error", "Git 管理器未初始化"

            elif name == "git_diff":
                path = params.get("path")
                if self.git_manager:
                    return "success", self.git_manager.diff(self.project_root, path)
                return "error", "Git 管理器未初始化"

            elif name == "git_commit":
                message = params.get("message", "")
                if not self._check_permission("git_commit", {"message": message}):
                    return "denied", "用户拒绝了提交操作"
                if self.git_manager:
                    return "success", self.git_manager.commit(self.project_root, message)
                return "error", "Git 管理器未初始化"

            elif name == "git_branch":
                action = params.get("action", "list")
                name_branch = params.get("name", "")
                if self.git_manager:
                    if action == "list":
                        return "success", self.git_manager.list_branches(self.project_root)
                    elif action == "switch":
                        return "success", self.git_manager.switch_branch(self.project_root, name_branch)
                    elif action == "create":
                        return "success", self.git_manager.create_branch(self.project_root, name_branch)
                return "error", "Git 管理器未初始化"

            elif name == "search_files":
                pattern = params.get("pattern", "")
                limit = params.get("limit", 50)
                if self.search_engine:
                    results = self.search_engine.search_files(self.project_root, pattern, limit)
                    return "success", json.dumps(results, ensure_ascii=False, indent=2)
                return "error", "搜索引擎未初始化"

            elif name == "search_code":
                query = params.get("query", "")
                limit = params.get("limit", 50)
                if self.search_engine:
                    results = self.search_engine.search_code(self.project_root, query, limit)
                    return "success", json.dumps(results, ensure_ascii=False, indent=2)
                return "error", "搜索引擎未初始化"

            elif name == "list_dir":
                path = self._resolve_path(params.get("path", "."))
                if self.file_manager:
                    items = self.file_manager.list_dir(path)
                    return "success", json.dumps(items, ensure_ascii=False, indent=2)
                return "error", "文件管理器未初始化"

            else:
                return "error", f"未知工具: {name}"

        except Exception as e:
            return "error", f"{str(e)}\n{traceback.format_exc()}"

    # ============ 主循环 ============
    def chat(self, user_message: str, max_steps: int = 20) -> str:
        """
        处理用户消息，主循环：
        1. 发送给模型
        2. 解析工具调用
        3. 执行工具
        4. 将结果返回给模型
        5. 重复直到没有工具调用或达到最大步数
        """
        task = AgentTask()
        self._current_task = task
        if self.on_task_start:
            self.on_task_start(task)

        # 保存用户消息
        self._messages.append(ChatMessage(role=ROLE_USER, content=user_message))
        if self.conversation_id:
            self.db.add_message(self.conversation_id, ROLE_USER, user_message)
        if self.on_message:
            self.on_message(ROLE_USER, user_message)

        full_response = ""
        reached_max_steps = False
        rethrow: Optional[BaseException] = None
        try:
            for step in range(max_steps):
                # 构建请求消息（系统提示 + 历史）
                messages = [ChatMessage(role=ROLE_SYSTEM, content=SYSTEM_PROMPT)]
                messages.extend(self._messages)

                # 调用模型（流式）；工具调用之后的新一轮输出另开新气泡展示
                if step > 0 and self.on_stream_turn:
                    try:
                        self.on_stream_turn()
                    except Exception:
                        pass
                assistant_content = ""
                if self.on_token:
                    # 流式输出
                    for chunk in self.model.chat_stream(messages):
                        assistant_content += chunk
                        self.on_token(chunk)
                else:
                    resp = self.model.chat(messages)
                    assistant_content = resp.content

                # 保存助手消息
                self._messages.append(ChatMessage(role=ROLE_ASSISTANT, content=assistant_content))
                if self.conversation_id:
                    self.db.add_message(self.conversation_id, ROLE_ASSISTANT, assistant_content)

                full_response = assistant_content

                # 解析工具调用
                tool_calls = TOOL_PATTERN.findall(assistant_content)
                if not tool_calls:
                    # 没有工具调用，结束
                    break

                # 执行每个工具调用
                tool_results = []
                for tool_name, tool_params_str in tool_calls:
                    try:
                        params = json.loads(tool_params_str.strip())
                    except json.JSONDecodeError:
                        params = {"raw": tool_params_str.strip()}

                    if self.on_tool_call:
                        self.on_tool_call(tool_name, params)
                    task.tool_calls.append({"name": tool_name, "params": params})

                    status, result = self._execute_tool(tool_name, params)
                    if self.on_tool_result:
                        self.on_tool_result(tool_name, result)

                    result_text = str(result) if not isinstance(result, str) else result
                    # 截断过长的结果
                    if len(result_text) > 8000:
                        result_text = result_text[:4000] + "\n... (结果已截断) ...\n" + result_text[-4000:]

                    tool_results.append(
                        f"<<<RESULT:{tool_name}|{status}>>>\n{result_text}\n<<<END_RESULT>>>"
                    )

                # 将工具结果作为用户消息加入上下文，让模型继续
                combined_result = "\n\n".join(tool_results)
                self._messages.append(ChatMessage(role=ROLE_USER, content=combined_result))
                # 不保存工具结果到数据库（避免污染历史），但标记一下
                if self.conversation_id:
                    self.db.add_message(
                        self.conversation_id, ROLE_USER, combined_result,
                        msg_type="tool_result",
                        metadata={"tool_results": True},
                    )
            else:
                # for 循环自然耗尽（每一步都有工具调用，未能在 max_steps 内收敛）
                reached_max_steps = True

            if reached_max_steps:
                task.status = TASK_FAILED
                task.error = f"达到最大步骤数 {max_steps}，任务未完成"
                task.result = full_response
                full_response = f"{full_response}\n\n⚠ 已达到最大步骤数（{max_steps}），任务可能未完成"
            else:
                task.status = TASK_SUCCESS
                task.result = full_response

        except Exception as e:
            # 记录状态与错误消息后继续向上抛出，让调用方（UI 线程包装）能实时展示错误
            task.status = TASK_FAILED
            task.error = f"{str(e)}\n{traceback.format_exc()}"
            full_response = f"执行出错: {str(e)}"
            if self.conversation_id:
                try:
                    self.db.add_message(self.conversation_id, ROLE_ASSISTANT, full_response, msg_type="error")
                except Exception:
                    pass
            rethrow = e

        task.end_time = time.time()
        self._current_task = None
        if self.on_task_end:
            self.on_task_end(task)

        # 记录操作日志
        try:
            self.db.add_log(
                action="agent_chat",
                detail=f"steps={len(task.tool_calls)}, duration={task.duration}s",
                status=task.status,
                duration=task.duration,
            )
        except Exception:
            pass

        if rethrow is not None:
            raise rethrow  # type: ignore[misc]

        return full_response

    def get_current_task(self) -> Optional[AgentTask]:
        return self._current_task

    def clear_context(self):
        """清空当前对话上下文"""
        self._messages = []
        self.conversation_id = None
