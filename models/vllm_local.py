"""vLLM 本地模型 - 通过 OpenAI 兼容接口调用本地部署的模型"""
from typing import Iterator, List

from openai import OpenAI

from models.base import BaseModel, ChatMessage, ModelResponse


class VLLMLocalModel(BaseModel):
    """vLLM 本地部署模型（OpenAI 兼容接口）"""

    def __init__(self, config):
        super().__init__(config)
        self._client = None

    def _get_client(self) -> OpenAI:
        if self._client is None:
            kwargs = {
                "api_key": self.config.get("vllm_api_key", "EMPTY"),
                "base_url": self.config.get("vllm_api_base", "http://localhost:8000/v1"),
            }
            self._client = OpenAI(**kwargs)
        return self._client

    def chat(self, messages: List[ChatMessage], **kwargs) -> ModelResponse:
        client = self._get_client()
        params = self._build_params(messages, config_prefix="vllm_", **kwargs)
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
        params = self._build_params(messages, config_prefix="vllm_", **kwargs)
        params["stream"] = True
        stream = client.chat.completions.create(**params)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def get_model_name(self) -> str:
        return self.config.get("vllm_model", "deepseek-coder-6.7b-instruct")

    def is_available(self) -> bool:
        """检查本地 vLLM 服务是否在运行"""
        try:
            import httpx
            base = self.config.get("vllm_api_base", "http://localhost:8000/v1")
            # vLLM 提供 /models 端点
            url = base.rstrip("/").replace("/v1", "") + "/models"
            resp = httpx.get(url, timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_local_models(self) -> List[str]:
        """列出本地 vLLM 可用的模型"""
        try:
            import httpx
            base = self.config.get("vllm_api_base", "http://localhost:8000/v1")
            url = base.rstrip("/").replace("/v1", "") + "/models"
            resp = httpx.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            pass
        return []
