"""DeepSeek API 模型 - 通过 OpenAI 兼容接口调用"""
from typing import Iterator, List

from openai import OpenAI

from models.base import BaseModel, ChatMessage, ModelResponse


class DeepSeekModel(BaseModel):
    """DeepSeek 云端模型"""

    def __init__(self, config):
        super().__init__(config)
        self._client = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            kwargs = {
                "api_key": self.config.get("deepseek_api_key", ""),
                "base_url": self.config.get("deepseek_api_base", "https://api.deepseek.com/v1"),
            }
            proxy = self.config.get_proxy_dict()
            if proxy:
                import httpx
                kwargs["http_client"] = httpx.Client(proxy=proxy)
            self._client = OpenAI(**kwargs)
        return self._client

    def chat(self, messages: List[ChatMessage], **kwargs) -> ModelResponse:
        client = self._get_client()
        params = self._build_params(messages, config_prefix="deepseek_", **kwargs)
        params["stream"] = False
        resp = client.chat.completions.create(**params)
        choice = resp.choices[0]
        return ModelResponse(
            content=choice.message.content or "",
            model=resp.model,
            finish_reason=choice.finish_reason or "",
            usage=dict(resp.usage) if resp.usage else {},
            raw=resp,
        )

    def chat_stream(self, messages: List[ChatMessage], **kwargs) -> Iterator[str]:
        client = self._get_client()
        params = self._build_params(messages, config_prefix="deepseek_", **kwargs)
        params["stream"] = True
        stream = client.chat.completions.create(**params)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_model_name(self) -> str:
        return self.config.get("deepseek_model", "deepseek-coder")

    def is_available(self) -> bool:
        return bool(self.config.get("deepseek_api_key", ""))
