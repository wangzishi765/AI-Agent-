"""
自动更新模块
检查新版本、下载更新、一键更新
"""
import os
import tempfile
import subprocess
import sys
from typing import Optional, Dict, Tuple

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from packaging import version
    VERSION_AVAILABLE = True
except ImportError:
    VERSION_AVAILABLE = False

from app.constants import APP_VERSION


class Updater:
    """应用自动更新器"""

    # 更新服务器地址（可配置）
    UPDATE_API = "https://api.github.com/repos/CodeAgent/CodeAgent/releases/latest"
    DOWNLOAD_URL_TEMPLATE = "https://github.com/CodeAgent/CodeAgent/releases/download/v{version}/CodeAgent-Setup-v{version}.exe"

    def __init__(self, config=None):
        self.config = config
        self._latest_version: Optional[str] = None
        self._release_info: Optional[Dict] = None

    def check_for_updates(self) -> Tuple[bool, str, str]:
        """
        检查更新
        返回: (有更新, 最新版本号, 更新说明)
        """
        if not REQUESTS_AVAILABLE:
            return False, APP_VERSION, "requests 库未安装"

        try:
            proxy = self.config.get_proxy_dict() if self.config else None
            kwargs = {"timeout": 10}
            if proxy:
                kwargs["proxies"] = proxy

            resp = requests.get(self.UPDATE_API, **kwargs)
            if resp.status_code != 200:
                return False, APP_VERSION, f"检查失败: HTTP {resp.status_code}"

            data = resp.json()
            latest = data.get("tag_name", "").lstrip("v")
            body = data.get("body", "")

            self._latest_version = latest
            self._release_info = data

            if VERSION_AVAILABLE:
                has_update = version.parse(latest) > version.parse(APP_VERSION)
            else:
                has_update = latest != APP_VERSION

            return has_update, latest, body

        except Exception as e:
            return False, APP_VERSION, f"检查失败: {str(e)}"

    def get_download_url(self, version: str = None) -> str:
        """获取下载链接"""
        ver = version or self._latest_version or APP_VERSION
        return self.DOWNLOAD_URL_TEMPLATE.format(version=ver)

    def download_update(self, version: str = None, callback=None) -> Optional[str]:
        """
        下载更新安装包
        callback(downloaded_bytes, total_bytes)
        返回下载的文件路径
        """
        if not REQUESTS_AVAILABLE:
            return None

        url = self.get_download_url(version)
        try:
            proxy = self.config.get_proxy_dict() if self.config else None
            kwargs = {"stream": True, "timeout": 30}
            if proxy:
                kwargs["proxies"] = proxy

            resp = requests.get(url, **kwargs)
            if resp.status_code != 200:
                return None

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            temp_path = os.path.join(tempfile.gettempdir(), f"CodeAgent-Setup-v{version or 'latest'}.exe")

            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if callback:
                            callback(downloaded, total)

            return temp_path

        except Exception:
            return None

    def apply_update(self, installer_path: str):
        """
        应用更新：运行安装包并退出当前程序
        """
        if not os.path.exists(installer_path):
            return False

        try:
            # 启动安装包（静默安装）
            if sys.platform == "win32":
                subprocess.Popen([installer_path, "/VERYSILENT", "/NORESTART"],
                                 close_fds=True)
            else:
                subprocess.Popen([installer_path], close_fds=True)

            # 退出当前程序
            try:
                from PySide6.QtWidgets import QApplication
                qapp = QApplication.instance()
                if qapp is not None:
                    qapp.quit()
                else:
                    os._exit(0)
            except Exception:
                os._exit(0)

            return True
        except Exception:
            return False

    def get_current_version(self) -> str:
        return APP_VERSION
