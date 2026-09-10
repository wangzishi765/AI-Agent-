"""搜索引擎 - 文件名搜索 + 全局代码内容搜索"""
import os
import re
from typing import Dict, List, Optional

try:
    import pathspec
    PATHSPEC_AVAILABLE = True
except ImportError:
    PATHSPEC_AVAILABLE = False


class SearchEngine:
    """文件和代码搜索引擎"""

    # 默认忽略目录
    DEFAULT_IGNORE_DIRS = {
        ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
        "env", ".env", "dist", "build", "target", "bin", "obj", ".idea",
        ".vscode", ".next", ".nuxt", "coverage", ".pytest_cache", ".mypy_cache",
        "vendor", "bower_components", ".cache", "tmp", "temp",
    }

    # 二进制文件扩展名
    BINARY_EXTS = {
        ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o", ".a", ".lib",
        ".pyc", ".pyo", ".class", ".jar", ".war", ".ear",
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
        ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
        ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".woff", ".woff2", ".ttf", ".eot",
        ".db", ".sqlite", ".sqlite3",
    }

    def __init__(self, config=None):
        self.config = config

    def _load_gitignore(self, root: str) -> Optional["pathspec.PathSpec"]:
        """加载 .gitignore"""
        if not PATHSPEC_AVAILABLE:
            return None
        gitignore_path = os.path.join(root, ".gitignore")
        if not os.path.exists(gitignore_path):
            return None
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                return pathspec.PathSpec.from_lines("gitwildmatch", f)
        except Exception:
            return None

    def _should_ignore(self, path: str, root: str, spec) -> bool:
        """判断是否应该忽略"""
        rel_path = os.path.relpath(path, root)
        name = os.path.basename(path)

        # 忽略目录
        if os.path.isdir(path) and name in self.DEFAULT_IGNORE_DIRS:
            return True

        # 忽略隐藏文件
        if name.startswith(".") and name not in (".gitignore", ".env.example"):
            return True

        # .gitignore 规则
        if spec:
            try:
                if spec.match_file(rel_path):
                    return True
            except Exception:
                pass

        return False

    def _is_text_file(self, path: str) -> bool:
        """判断是否为文本文件"""
        ext = os.path.splitext(path)[1].lower()
        if ext in self.BINARY_EXTS:
            return False
        try:
            with open(path, "rb") as f:
                chunk = f.read(4096)
            return b"\x00" not in chunk
        except Exception:
            return False

    def search_files(self, root: str, pattern: str, limit: int = 50) -> List[Dict]:
        """
        按文件名搜索（模糊匹配）
        """
        if not root or not os.path.exists(root):
            return []

        pattern_lower = pattern.lower()
        results = []
        spec = self._load_gitignore(root)

        for dirpath, dirnames, filenames in os.walk(root):
            # 过滤忽略目录
            dirnames[:] = [
                d for d in dirnames
                if not self._should_ignore(os.path.join(dirpath, d), root, spec)
            ]

            for filename in filenames:
                if pattern_lower in filename.lower():
                    full_path = os.path.join(dirpath, filename)
                    if self._should_ignore(full_path, root, spec):
                        continue
                    results.append({
                        "path": full_path,
                        "name": filename,
                        "relative_path": os.path.relpath(full_path, root),
                        "is_dir": False,
                        "match_score": self._match_score(filename, pattern),
                    })
                    if len(results) >= limit:
                        return sorted(results, key=lambda x: -x["match_score"])

        return sorted(results, key=lambda x: -x["match_score"])

    def _match_score(self, filename: str, pattern: str) -> int:
        """计算匹配分数，用于排序"""
        name_lower = filename.lower()
        pattern_lower = pattern.lower()
        score = 0
        if name_lower == pattern_lower:
            score += 100
        elif name_lower.startswith(pattern_lower):
            score += 50
        elif pattern_lower in name_lower:
            score += 20
        return score

    def search_code(self, root: str, query: str, limit: int = 50,
                    case_sensitive: bool = False, use_regex: bool = False) -> List[Dict]:
        """
        全局搜索代码内容
        """
        if not root or not os.path.exists(root):
            return []

        results = []
        spec = self._load_gitignore(root)

        if use_regex:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                pattern = re.compile(query, flags)
            except re.error:
                return []
        else:
            pattern = None

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if not self._should_ignore(os.path.join(dirpath, d), root, spec)
            ]

            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                if self._should_ignore(full_path, root, spec):
                    continue
                if not self._is_text_file(full_path):
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                file_matches = []
                for line_num, line in enumerate(lines, 1):
                    if use_regex and pattern:
                        if pattern.search(line):
                            file_matches.append({
                                "line": line_num,
                                "content": line.rstrip("\n"),
                            })
                    else:
                        search_line = line if case_sensitive else line.lower()
                        search_query = query if case_sensitive else query.lower()
                        if search_query in search_line:
                            file_matches.append({
                                "line": line_num,
                                "content": line.rstrip("\n"),
                            })

                if file_matches:
                    results.append({
                        "path": full_path,
                        "name": filename,
                        "relative_path": os.path.relpath(full_path, root),
                        "matches": file_matches,
                        "match_count": len(file_matches),
                    })
                    if len(results) >= limit:
                        return sorted(results, key=lambda x: -x["match_count"])

        return sorted(results, key=lambda x: -x["match_count"])
