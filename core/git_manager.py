"""Git 管理器 - 深度集成 Git 操作"""
from typing import Dict, List, Optional

try:
    from git import Repo, GitCommandError, InvalidGitRepositoryError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False


class GitManager:
    """Git 操作管理器"""

    def __init__(self, config=None):
        self.config = config

    def is_repo(self, path: str) -> bool:
        """检查是否为 Git 仓库"""
        if not GIT_AVAILABLE:
            return False
        try:
            Repo(path, search_parent_directories=True)
            return True
        except (InvalidGitRepositoryError, Exception):
            return False

    def _get_repo(self, path: str) -> Optional[Repo]:
        if not GIT_AVAILABLE:
            return None
        try:
            return Repo(path, search_parent_directories=True)
        except Exception:
            return None

    def status(self, path: str) -> str:
        """获取 Git 状态"""
        repo = self._get_repo(path)
        if not repo:
            return "不是 Git 仓库"
        try:
            return repo.git.status()
        except GitCommandError as e:
            return f"Git 错误: {e}"

    def diff(self, path: str, file_path: Optional[str] = None) -> str:
        """获取 diff"""
        repo = self._get_repo(path)
        if not repo:
            return "不是 Git 仓库"
        try:
            if file_path:
                return repo.git.diff(file_path)
            return repo.git.diff()
        except GitCommandError as e:
            return f"Git 错误: {e}"

    def staged_diff(self, path: str) -> str:
        """获取已暂存的 diff"""
        repo = self._get_repo(path)
        if not repo:
            return "不是 Git 仓库"
        try:
            return repo.git.diff("--cached")
        except GitCommandError as e:
            return f"Git 错误: {e}"

    def commit(self, path: str, message: str) -> str:
        """提交更改（自动 add 所有更改）"""
        repo = self._get_repo(path)
        if not repo:
            return "错误: 不是 Git 仓库"
        try:
            repo.git.add(A=True)
            if not repo.is_dirty(staged=True):
                return "没有可提交的更改"
            commit = repo.index.commit(message)
            return f"提交成功: {commit.hexsha[:8]} - {message}"
        except GitCommandError as e:
            return f"提交失败: {e}"

    def list_branches(self, path: str) -> str:
        """列出所有分支"""
        repo = self._get_repo(path)
        if not repo:
            return "不是 Git 仓库"
        try:
            try:
                current = repo.active_branch.name
            except (TypeError, ValueError):
                # 无提交的新仓库（unborn HEAD）没有活动分支
                return "当前分支: (暂无提交)\n\n尚未创建任何提交，请先 commit 一次。"
            branches = [h.name for h in repo.branches]
            result = f"当前分支: {current}\n\n所有分支:\n"
            for b in branches:
                marker = "*" if b == current else " "
                result += f"  {marker} {b}\n"
            return result
        except GitCommandError as e:
            return f"Git 错误: {e}"

    def switch_branch(self, path: str, branch_name: str) -> str:
        """切换分支"""
        repo = self._get_repo(path)
        if not repo:
            return "错误: 不是 Git 仓库"
        try:
            repo.git.checkout(branch_name)
            return f"已切换到分支: {branch_name}"
        except GitCommandError as e:
            return f"切换失败: {e}"

    def create_branch(self, path: str, branch_name: str) -> str:
        """创建并切换到新分支"""
        repo = self._get_repo(path)
        if not repo:
            return "错误: 不是 Git 仓库"
        try:
            repo.git.checkout("-b", branch_name)
            return f"已创建并切换到分支: {branch_name}"
        except GitCommandError as e:
            return f"创建分支失败: {e}"

    def log(self, path: str, count: int = 20) -> str:
        """查看提交历史"""
        repo = self._get_repo(path)
        if not repo:
            return "不是 Git 仓库"
        try:
            return repo.git.log(f"-{count}", "--oneline", "--graph", "--decorate")
        except GitCommandError as e:
            return f"Git 错误: {e}"

    def pull(self, path: str) -> str:
        """拉取最新代码"""
        repo = self._get_repo(path)
        if not repo:
            return "错误: 不是 Git 仓库"
        try:
            result = repo.remotes.origin.pull()
            return f"拉取成功: {result[0].commit.hexsha[:8] if result else 'already up to date'}"
        except Exception as e:
            return f"拉取失败: {e}"

    def push(self, path: str) -> str:
        """推送代码"""
        repo = self._get_repo(path)
        if not repo:
            return "错误: 不是 Git 仓库"
        try:
            repo.remotes.origin.push()
            return "推送成功"
        except Exception as e:
            return f"推送失败: {e}"

    def get_changed_files(self, path: str) -> List[Dict]:
        """获取变更文件列表"""
        repo = self._get_repo(path)
        if not repo:
            return []
        try:
            files = []
            # 未暂存的更改
            for diff in repo.index.diff(None):
                files.append({
                    "path": diff.a_path,
                    "status": "modified" if diff.change_type == "M" else diff.change_type,
                    "staged": False,
                })
            # 已暂存的更改（无提交的新仓库没有 HEAD，跳过已暂存部分）
            try:
                for diff in repo.index.diff("HEAD"):
                    files.append({
                        "path": diff.a_path,
                        "status": "modified" if diff.change_type == "M" else diff.change_type,
                        "staged": True,
                    })
            except Exception:
                pass
            # 未跟踪文件
            for f in repo.untracked_files:
                files.append({"path": f, "status": "untracked", "staged": False})
            return files
        except Exception:
            return []
