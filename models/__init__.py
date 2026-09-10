"""AI 模型层 - 统一封装 DeepSeek 和 vLLM 本地模型"""
from models.base import BaseModel, ModelResponse, ChatMessage
from models.deepseek import DeepSeekModel
from models.vllm_local import VLLMLocalModel
from models.completion import CodeCompleter


def get_model(model_type: str, config) -> BaseModel:
    """工厂方法：根据类型创建模型实例"""
    if model_type == "deepseek":
        return DeepSeekModel(config)
    elif model_type == "vllm_local":
        return VLLMLocalModel(config)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


__all__ = [
    "BaseModel", "ModelResponse", "ChatMessage",
    "DeepSeekModel", "VLLMLocalModel", "CodeCompleter",
    "get_model",
]
