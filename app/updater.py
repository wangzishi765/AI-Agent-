"""
自动更新模块
对接 GitHub Releases：检查新版本、下载安装包、一键更新
"""
import os
import subprocess
import sys
import tempfile
from typing import Callable, Dict, Optional, Tuple

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
    """应用自动更新器（数据源：GitHub Releases）"""

    # 你的仓库（发布新版本时打 tag，例如 v1.1.0，CI 会自动把安装包挂到 Release）
    REPO = "wangzishi765/AI-Agent-"
    UPDATE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
    RELEASES_PAGE = f"https://github.com/{REPO}/releases"
    DOWNLOAD_URL_TEMPLATE = (
        f"https://github.com/{REPO}/releases/download/v{{version}}/"
        f"CodeAgent-Setup-v{{version}}.exe"
    )
    # 只信任 GitHub 域名下的下载地址
    TRUSTED_HOSTS = ("github.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com")

    def __init__(self, config=None):
        self.config = config
        self._latest_version: Optional[str] = None
        self._release_info: Optional[Dict] = None
        self._asset_url: str = ""
        self._asset_size: int = 0

    # ---------- 内部工具 ----------
    def _request_kwargs(self, stream: bool = False) -> Dict:
        kwargs = {
            "timeout": 30 if stream else 10,
            "headers": {
                "User-Agent": "CodeAgent-Updater",
                "Accept": "application/vnd.github+json",
            },
        }
        proxy = self.config.get_proxy_dict() if self.config else None
        if proxy:
            kwargs["proxies"] = proxy
        return kwargs

    @staticmethod
    def _pick_installer_asset(data: Dict) -> Tuple[str, int]:
        """从 Release 附件中挑选安装包（CodeAgent-Setup-*.exe）"""
        best_url, best_size = "", 0
        for asset in data.get("assets") or []:
            name = (asset.get("name") or "").lower()
            if not name.endswith(".exe"):
                continue
            url = asset.get("browser_download_url") or ""
            if "setup" in name:
                return url, int(asset.get("size") or 0)
            if not best_url:
                best_url, best_size = url, int(asset.get("size") or 0)
        return best_url, best_size

    # ---------- 检查更新 ----------
    def check_for_updates(self) -> Tuple[bool, str, str]:
        """
        检查更新
        返回: (有更新, 最新版本号, 更新说明 / 错误信息)
        """
        if not REQUESTS_AVAILABLE:
            return False, APP_VERSION, "requests 库未安装"

        try:
            resp = requests.get(self.UPDATE_API, **self._request_kwargs())
        except Exception as e:
            return False, APP_VERSION, f"检查失败: {str(e)}"

        if resp.status_code == 404:
            return False, APP_VERSION, "检查失败: 仓库暂无 Release"
        if resp.status_code == 403:
            return False, APP_VERSION, "检查失败: GitHub API 访问频率受限，请稍后再试"
        if resp.status_code != 200:
            return False, APP_VERSION, f"检查失败: HTTP {resp.status_code}"

        try:
            data = resp.json()
        except Exception:
            return False, APP_VERSION, "检查失败: 返回内容无法解析"

        latest = (data.get("tag_name") or "").lstrip("v").strip()
        if not latest:
            return False, APP_VERSION, "检查失败: Release 未设置 tag"

        self._latest_version = latest
        self._release_info = data
        self._asset_url, self._asset_size = self._pick_installer_asset(data)

        if VERSION_AVAILABLE:
            try:
                has_update = version.parse(latest) > version.parse(APP_VERSION)
            except Exception:
                has_update = latest != APP_VERSION
        else:
            has_update = latest != APP_VERSION

        body = data.get("body") or data.get("name") or ""
        return has_update, latest, body

    # ---------- 下载 ----------
    def get_download_url(self, version: str = None) -> str:
        """获取安装包下载链接：优先用 Release 里的真实附件地址"""
        ver = (version or self._latest_version or APP_VERSION).lstrip("v")
        if self._asset_url and ver == (self._latest_version or ""):
            return self._asset_url
        return self.DOWNLOAD_URL_TEMPLATE.format(version=ver)

    def download_update(self, version: str = None,
                        callback: Optional[Callable[[int, int], None]] = None) -> Optional[str]:
        """
        下载更新安装包
        callback(downloaded_bytes, total_bytes)
        返回下载的文件路径；失败返回 None
        """
        if not REQUESTS_AVAILABLE:
            return None

        url = self.get_download_url(version)
        if not url:
            return None
        host = url.split("/")[2] if "://" in url else ""
        if host and host not in self.TRUSTED_HOSTS:
            return None

        try:
            kwargs = self._request_kwargs(stream=True)
            resp = requests.get(url, stream=True, **kwargs)
            if resp.status_code != 200:
                return None

            total = int(resp.headers.get("content-length") or self._asset_size or 0)
            downloaded = 0
            temp_path = os.path.join(
                tempfile.gettempdir(),
                f"CodeAgent-Setup-v{version or self._latest_version or 'latest'}.exe",
            )

            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=256 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if callback:
                        try:
                            callback(downloaded, total)
                        except Exception:
                            pass

            # 大小校验（能拿到总数时必须一致，避免半包）
            if total and downloaded != total:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                return None
            return temp_path

        except Exception:
            return None

    # ---------- 安装 ----------
    def apply_update(self, installer_path: str) -> bool:
        """运行安装包并退出当前程序"""
        if not installer_path or not os.path.exists(installer_path):
            return False

        try:
            if sys.platform == "win32":
                subprocess.Popen([installer_path, "/VERYSILENT", "/NORESTART"], close_fds=True)
            else:
                subprocess.Popen([installer_path], close_fds=True)

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

    def get_release_page(self) -> str:
        """Release 列表页（手动下载/查看更新日志用）"""
        return f"{self.RELEASES_PAGE}/tag/v{self._latest_version}" if self._latest_version else self.RELEASES_PAGE
