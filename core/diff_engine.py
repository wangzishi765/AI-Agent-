"""Diff 对比引擎 - 生成改前/改后对比"""
import difflib
from typing import Dict, List


class DiffEngine:
    """代码 Diff 对比引擎"""

    @staticmethod
    def unified_diff(old_text: str, new_text: str, old_label: str = "修改前",
                     new_label: str = "修改后", n: int = 3) -> str:
        """生成 unified diff 格式"""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=old_label, tofile=new_label,
            n=n,
        )
        return "".join(diff)

    @staticmethod
    def side_by_side(old_text: str, new_text: str, width: int = 80) -> str:
        """生成并排对比"""
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()
        diff = difflib.ndiff(old_lines, new_lines)
        result = []
        for line in diff:
            result.append(line)
        return "\n".join(result)

    @staticmethod
    def parse_diff(diff_text: str) -> List[Dict]:
        """解析 unified diff，返回结构化的变更块"""
        blocks = []
        current_block = None
        lines = diff_text.split("\n")

        for line in lines:
            if line.startswith("@@"):
                if current_block:
                    blocks.append(current_block)
                current_block = {"header": line, "lines": []}
            elif current_block is not None:
                current_block["lines"].append(line)

        if current_block:
            blocks.append(current_block)

        return blocks

    @staticmethod
    def compare_files(old_content: str, new_content: str) -> Dict:
        """
        对比两个文件内容，返回详细对比信息
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        # 统计变更
        added = 0
        removed = 0
        modified = 0

        sm = difflib.SequenceMatcher(None, old_lines, new_lines)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace":
                modified += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "insert":
                added += j2 - j1

        return {
            "added": added,
            "removed": removed,
            "modified": modified,
            "old_line_count": len(old_lines),
            "new_line_count": len(new_lines),
            "unified_diff": DiffEngine.unified_diff(old_content, new_content),
            "has_changes": old_content != new_content,
            "similarity": round(sm.ratio() * 100, 2),
        }

    @staticmethod
    def highlight_diff(diff_text: str) -> List[Dict]:
        """将 diff 文本转为带高亮类型的行列表"""
        result = []
        for line in diff_text.split("\n"):
            if line.startswith("+++") or line.startswith("---"):
                htype = "header"
            elif line.startswith("@@"):
                htype = "hunk"
            elif line.startswith("+"):
                htype = "added"
            elif line.startswith("-"):
                htype = "removed"
            elif line.startswith(" "):
                htype = "context"
            else:
                htype = "normal"
            result.append({"text": line, "type": htype})
        return result
