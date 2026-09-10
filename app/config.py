"""配置管理 - 基于 JSON 的用户配置"""
import json
import os
from typing import Any, Dict, Optional

from app.constants import (
    DEFAULT_DATA_DIR, DEFAULT_SHORTCUTS, PERMISSION_FULL, MODEL_DEEPSEEK,
)


class Config:
    """全局配置管理器"""

    DEFAULTS: Dict[str, Any] = {
        # 基本
        "language": "zh_CN",
        "theme": "light",
        "window_width": 1400,
        "window_height": 900,

        # 权限
        "permission_mode": PERMISSION_FULL,

        # AI 模型
        "active_model": MODEL_DEEPSEEK,
        "deepseek_api_key": "",
        "deepseek_api_base": "https://api.deepseek.com/v1",
        "deepseek_model": "deepseek-coder",
        "deepseek_temperature": 0.7,
        "deepseek_max_tokens": 4096,
        "vllm_api_base": "http://localhost:8000/v1",
        "vllm_api_key": "EMPTY",
        "vllm_model": "deepseek-coder-6.7b-instruct",
        "vllm_temperature": 0.7,
        "vllm_max_tokens": 4096,

        # 网络代理
        "proxy_enabled": False,
        "proxy_type": "http",  # http / https / socks5 / system
        "proxy_host": "",
        "proxy_port": "",
        "proxy_username": "",
        "proxy_password": "",

        # 代码执行
        "docker_enabled": True,
        "docker_image": "codeagent-exec:latest",
        "docker_timeout": 300,
        "docker_memory_limit": "2g",
        "docker_cpu_limit": 2,

        # 行为
        "close_to_tray": True,
        "auto_start": False,
        "auto_check_update": True,
        "show_diff_preview": True,
        "auto_format": True,
        "auto_lint": True,
        "show_task_duration": True,

        # 快捷键
        "shortcuts": DEFAULT_SHORTCUTS,

        # 语音
        "voice_enabled": True,
        "voice_language": "zh-CN",

        # OCR
        "ocr_enabled": True,
        "ocr_language": "chi_sim+eng",

        # 项目
        "recent_projects": [],
        "favorite_projects": [],
        "workspace_folders": [],
    }

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.config_file = os.path.join(self.data_dir, "config.json")
        self._data: Dict[str, Any] = {}
        self._ensure_dir()

    def _ensure_dir(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "db"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "snippets"), exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, "temp"), exist_ok=True)

    def load(self):
        """加载配置，缺失项用默认值填充"""
        self._data = dict(self.DEFAULTS)
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, IOError):
                pass  # 配置损坏时用默认值

    def save(self):
        """保存配置到文件"""
        self._ensure_dir()
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, autosave: bool = True):
        self._data[key] = value
        if autosave:
            self.save()

    def get_all(self) -> Dict[str, Any]:
        return dict(self._data)

    def update(self, data: Dict[str, Any], autosave: bool = True):
        self._data.update(data)
        if autosave:
            self.save()

    def reset(self, key: Optional[str] = None):
        if key:
            if key in self.DEFAULTS:
                self._data[key] = self.DEFAULTS[key]
        else:
            self._data = dict(self.DEFAULTS)
        self.save()

    def get_proxy_dict(self) -> Optional[Dict[str, str]]:
        """获取 requests/httpx 可用的代理字典"""
        if not self.get("proxy_enabled", False):
            return None
        ptype = self.get("proxy_type", "http")
        if ptype == "system":
            return None  # 走系统代理，不手动设置
        host = self.get("proxy_host", "")
        port = self.get("proxy_port", "")
        if not host or not port:
            return None
        auth = ""
        user = self.get("proxy_username", "")
        pwd = self.get("proxy_password", "")
        if user:
            auth = f"{user}:{pwd}@"
        url = f"{ptype}://{auth}{host}:{port}"
        return {"http://": url, "https://": url}
