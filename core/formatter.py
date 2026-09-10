"""代码格式化与 Linter 检查"""
import os
import shutil
import subprocess
from typing import Dict, List


class CodeFormatter:
    """代码格式化器和 Linter"""

    # 各语言格式化工具
    FORMATTERS = {
        "python": [
            {"cmd": ["black", "--quiet", "{file}"], "name": "black"},
            {"cmd": ["isort", "--quiet", "{file}"], "name": "isort"},
        ],
        "javascript": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "typescript": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "vue": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "css": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "html": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "json": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "markdown": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier"},
        ],
        "java": [
            {"cmd": ["npx", "prettier", "--write", "{file}"], "name": "prettier (plugin:java)"},
        ],
        "go": [
            {"cmd": ["gofmt", "-w", "{file}"], "name": "gofmt"},
        ],
        "rust": [
            {"cmd": ["rustfmt", "{file}"], "name": "rustfmt"},
        ],
        "c": [
            {"cmd": ["clang-format", "-i", "{file}"], "name": "clang-format"},
        ],
        "cpp": [
            {"cmd": ["clang-format", "-i", "{file}"], "name": "clang-format"},
        ],
    }

    # 各语言 Linter
    LINTERS = {
        "python": [
            {"cmd": ["flake8", "{file}"], "name": "flake8"},
            {"cmd": ["pylint", "{file}"], "name": "pylint"},
        ],
        "javascript": [
            {"cmd": ["npx", "eslint", "{file}"], "name": "eslint"},
        ],
        "typescript": [
            {"cmd": ["npx", "eslint", "{file}"], "name": "eslint"},
        ],
        "vue": [
            {"cmd": ["npx", "eslint", "{file}"], "name": "eslint"},
        ],
        "go": [
            {"cmd": ["go", "vet", "{file}"], "name": "go vet"},
        ],
        "rust": [
            {"cmd": ["cargo", "clippy", "--", "{file}"], "name": "clippy"},
        ],
    }

    def __init__(self, config=None):
        self.config = config

    def _get_language(self, file_path: str) -> str:
        from app.constants import CODE_EXTENSIONS
        ext = os.path.splitext(file_path)[1].lower()
        return CODE_EXTENSIONS.get(ext, "plaintext")

    def _run_tool(self, cmd: List[str], timeout: int = 30):
        """
        运行外部工具。

        Windows 上 npx/eslint/prettier 等只有 .cmd/.bat 垫片，
        CreateProcess 无法直接启动，必须经 cmd 解释；这里自动识别并切换。
        工具确实不存在时抛 FileNotFoundError，由调用方跳过。
        """
        run_kwargs = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            name = cmd[0]
            exe = shutil.which(name)
            if exe is None:
                # 存在 .cmd/.bat 垫片（如 npx.cmd）时经 cmd shell 运行
                if any(shutil.which(name + ext) for ext in (".cmd", ".bat")):
                    line = subprocess.list2cmdline(cmd)
                    return subprocess.run(line, shell=True, **run_kwargs)
                raise FileNotFoundError(f"可执行文件未找到: {name}")
            if os.path.splitext(exe)[1].lower() in (".cmd", ".bat"):
                line = subprocess.list2cmdline(cmd)
                return subprocess.run(line, shell=True, **run_kwargs)
        return subprocess.run(cmd, **run_kwargs)

    def format_file(self, file_path: str) -> Dict:
        """
        格式化文件
        返回: {"success": bool, "formatter": str, "output": str, "error": str}
        """
        language = self._get_language(file_path)
        formatters = self.FORMATTERS.get(language, [])

        if not formatters:
            return {"success": True, "formatter": "none", "output": "", "error": f"无格式化工具: {language}"}

        ran_any = False
        last_result = {"success": True, "formatter": "", "output": "", "error": ""}
        for fmt in formatters:
            cmd = [c.replace("{file}", file_path) for c in fmt["cmd"]]
            try:
                proc = self._run_tool(cmd)
                ran_any = True
                last_result = {
                    "success": proc.returncode == 0,
                    "formatter": fmt["name"],
                    "output": proc.stdout or "",
                    "error": proc.stderr or "",
                }
                if proc.returncode != 0:
                    break
            except FileNotFoundError:
                # 工具未安装，跳过
                continue
            except subprocess.TimeoutExpired:
                last_result = {"success": False, "formatter": fmt["name"], "output": "", "error": "超时"}
                ran_any = True
                break
            except Exception as e:
                last_result = {"success": False, "formatter": fmt["name"], "output": "", "error": str(e)}
                ran_any = True
                break

        if not ran_any:
            return {
                "success": False,
                "formatter": "none",
                "output": "",
                "error": f"未找到可用的格式化工具（{language}），请安装 black/isort/prettier 等",
            }
        return last_result

    def lint_file(self, file_path: str) -> Dict:
        """
        运行 Linter 检查
        返回: {"success": bool, "linter": str, "issues": List[str], "output": str, "error": str}
        """
        language = self._get_language(file_path)
        linters = self.LINTERS.get(language, [])

        if not linters:
            return {"success": True, "linter": "none", "issues": [], "output": "", "error": f"无 Linter: {language}"}

        all_issues = []
        ran_any = False
        for lint in linters:
            cmd = [c.replace("{file}", file_path) for c in lint["cmd"]]
            try:
                proc = self._run_tool(cmd)
                ran_any = True
                output = (proc.stdout or "") + (proc.stderr or "")
                if output.strip():
                    issues = [line for line in output.strip().split("\n") if line.strip()]
                    all_issues.extend(issues)
            except FileNotFoundError:
                continue
            except Exception:
                continue

        return {
            "success": ran_any,
            "linter": ",".join(l["name"] for l in linters),
            "issues": all_issues,
            "output": "\n".join(all_issues),
            "error": "" if ran_any else "未找到可用的 Linter 工具",
        }

    def format_and_lint(self, file_path: str) -> Dict:
        """格式化并检查"""
        fmt_result = self.format_file(file_path)
        lint_result = self.lint_file(file_path)
        return {
            "format": fmt_result,
            "lint": lint_result,
            "issues_count": len(lint_result.get("issues", [])),
        }
