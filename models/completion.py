"""代码自动补全 - 基于当前文件上下文和对话历史的 AI 补全"""
from typing import List

from models.base import ChatMessage


class CodeCompleter:
    """代码补全器，复用聊天模型做 FIM（Fill-In-Middle）补全"""

    SYSTEM_PROMPT = """你是一个专业的代码补全引擎。根据给定的代码上下文，预测接下来应该输入的代码。
规则：
1. 只输出补全的代码片段，不要解释，不要 markdown 代码块标记
2. 保持与现有代码的缩进和风格一致
3. 补全应该简洁、准确、符合语言习惯
4. 如果上下文不足以确定补全，给出最可能的补全"""

    def __init__(self, model):
        self.model = model

    def build_prompt(self, code_before: str, code_after: str = "",
                     language: str = "", conversation_context: str = "") -> List[ChatMessage]:
        """构建补全请求消息"""
        messages = [ChatMessage(role="system", content=self.SYSTEM_PROMPT)]

        user_content = f"编程语言: {language or 'unknown'}\n\n"
        if conversation_context:
            user_content += f"相关对话上下文:\n{conversation_context}\n\n"
        user_content += f"光标前的代码:\n```\n{code_before}\n```\n\n"
        if code_after:
            user_content += f"光标后的代码:\n```\n{code_after}\n```\n\n"
        user_content += "请直接输出光标位置应该补全的代码："

        messages.append(ChatMessage(role="user", content=user_content))
        return messages

    def complete(self, code_before: str, code_after: str = "",
                 language: str = "", conversation_context: str = "",
                 max_tokens: int = 128) -> str:
        """同步补全"""
        messages = self.build_prompt(code_before, code_after, language, conversation_context)
        try:
            resp = self.model.chat(messages, max_tokens=max_tokens, temperature=0.2)
            text = resp.content.strip()
            # 清理可能的 markdown 标记
            if text.startswith("```"):
                lines = text.split("\n")
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                text = "\n".join(lines)
            return text
        except Exception:
            return ""

    def complete_stream(self, code_before: str, code_after: str = "",
                        language: str = "", conversation_context: str = "",
                        max_tokens: int = 128):
        """流式补全"""
        messages = self.build_prompt(code_before, code_after, language, conversation_context)
        try:
            for chunk in self.model.chat_stream(messages, max_tokens=max_tokens, temperature=0.2):
                yield chunk
        except Exception:
            return
