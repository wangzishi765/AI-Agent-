"""模型基类 - 定义统一接口"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # system / user / assistant
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None

    def to_dict(self) -> Dict:
        d = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class ModelResponse:
    """模型响应"""
    content: str
    model: str = ""
    finish_reason: str = ""
    usage: Dict[str, int] = field(default_factory=dict)
    raw: Any = None

    @property
    def prompt_tokens(self) -> int:
        return self.usage.get("prompt_tokens", 0)

    @property
    def completion_tokens(self) -> int:
        return self.usage.get("completion_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


class BaseModel(ABC):
    """模型基类"""

    def __init__(self, config):
        self.config = config
        self._client = None

    @abstractmethod
    def chat(self, messages: List[ChatMessage], **kwargs) -> ModelResponse:
        """同步聊天"""
        ...

    @abstractmethod
    def chat_stream(self, messages: List[ChatMessage], **kwargs) -> Iterator[str]:
        """流式聊天，逐块产出文本"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """返回当前模型名称"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查模型是否可用"""
        ...

    def _build_params(self, messages: List[ChatMessage], **kwargs) -> Dict:
        """构建请求参数"""
        prefix = kwargs.get("config_prefix", "")
        temp_key = f"{prefix}temperature" if prefix else "temperature"
        max_key = f"{prefix}max_tokens" if prefix else "max_tokens"
        model_key = f"{prefix}model" if prefix else "model"

        params = {
            "model": kwargs.get("model") or self.config.get(model_key, ""),
            "messages": [m.to_dict() for m in messages],
            "temperature": kwargs.get("temperature", self.config.get(temp_key, 0.7)),
            "max_tokens": kwargs.get("max_tokens", self.config.get(max_key, 4096)),
            "stream": kwargs.get("stream", False),
        }
        # 移除空值
        return {k: v for k, v in params.items() if v is not None}
