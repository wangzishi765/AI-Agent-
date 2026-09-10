"""文件管理器 - 读写文件、列出目录、编辑文件"""
import os
import shutil
from typing import Dict, List, Optional

from app.constants import CODE_EXTENSIONS


class FileManager:
    """文件操作管理器"""

    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB 上限

    def __init__(self, config=None):
        self.config = config

    def read_file(self, path: str, max_size: int = MAX_FILE_SIZE) -> str:
        """读取文件内容"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        if not os.path.isfile(path):
            raise IsADirectoryError(f"不是文件: {path}")

        size = os.path.getsize(path)
        if size > max_size:
            raise ValueError(f"文件过大 ({size} bytes)，超过限制 ({max_size} bytes)")

        # 尝试多种编码（latin-1 会吞掉任意字节，不能直接作为兜底，
        # 否则二进制文件会被当作文本返回；用它解码后再做 NUL 检测）
        encodings = ["utf-8", "gbk", "gb2312"]
        for enc in encodings:
            try:
                with open(path, "r", encoding=enc) as f:
                    content = f.read()
                if "\x00" in content:
                    break
                return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        # 若已成功解码（含 NUL 二进制），上面 break 后走到这里；否则 latin-1 兜底
        try:
            with open(path, "r", encoding="latin-1") as f:
                content = f.read()
            if "\x00" in content:
                raise UnicodeDecodeError("binary", b"", 0, 1, "contains NUL")
        except (UnicodeDecodeError, UnicodeError):
            pass
        else:
            return content
        # 全部失败，按二进制读取并提示
        with open(path, "rb") as f:
            raw = f.read(2000)
        return f"[二进制文件，无法以文本读取] 前2000字节: {raw[:200]!r}"

    def write_file(self, path: str, content: str):
        """写入文件，自动创建目录"""
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def edit_file(self, path: str, old_text: str, new_text: str) -> bool:
        """编辑文件：替换指定文本。返回是否成功"""
        content = self.read_file(path)
        if old_text not in content:
            # 尝试去除首尾空白后匹配
            stripped = old_text.strip()
            if stripped and stripped in content:
                old_text = stripped
            else:
                raise ValueError("未找到要替换的文本，请确认 old_text 与文件内容完全匹配")

        new_content = content.replace(old_text, new_text, 1)
        self.write_file(path, new_content)
        return True

    def list_dir(self, path: str, show_hidden: bool = False) -> List[Dict]:
        """列出目录内容"""
        if not os.path.exists(path):
            raise FileNotFoundError(f"目录不存在: {path}")
        if not os.path.isdir(path):
            raise NotADirectoryError(f"不是目录: {path}")

        items = []
        try:
            for name in sorted(os.listdir(path)):
                if not show_hidden and name.startswith("."):
                    continue
                full_path = os.path.join(path, name)
                is_dir = os.path.isdir(full_path)
                items.append({
                    "name": name,
                    "path": full_path,
                    "is_dir": is_dir,
                    "size": os.path.getsize(full_path) if not is_dir else 0,
                    "extension": os.path.splitext(name)[1].lower(),
                })
        except PermissionError:
            pass
        return items

    def delete_file(self, path: str):
        """删除文件或目录"""
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    def move_file(self, src: str, dst: str):
        """移动/重命名文件"""
        directory = os.path.dirname(dst)
        if directory:
            os.makedirs(directory, exist_ok=True)
        shutil.move(src, dst)

    def copy_file(self, src: str, dst: str):
        """复制文件"""
        directory = os.path.dirname(dst)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    def get_language(self, path: str) -> str:
        """根据文件扩展名获取语言"""
        ext = os.path.splitext(path)[1].lower()
        return CODE_EXTENSIONS.get(ext, "plaintext")

    def is_text_file(self, path: str) -> bool:
        """判断是否为文本文件"""
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        if ext in CODE_EXTENSIONS:
            return True
        # 尝试读取前 1024 字节判断
        try:
            with open(path, "rb") as f:
                chunk = f.read(1024)
            return b"\x00" not in chunk
        except Exception:
            return False

    def get_file_info(self, path: str) -> Optional[Dict]:
        """获取文件信息"""
        if not os.path.exists(path):
            return None
        stat = os.stat(path)
        return {
            "path": path,
            "name": os.path.basename(path),
            "is_dir": os.path.isdir(path),
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "language": self.get_language(path),
        }
