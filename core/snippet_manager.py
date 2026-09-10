"""代码片段管理器 - 基于数据库的片段增删改查"""
from typing import Dict, List, Optional


class SnippetManager:
    """代码片段管理器"""

    def __init__(self, database):
        self.db = database

    def add(self, title: str, content: str, language: str = "",
            category: str = "默认", description: str = "",
            tags: Optional[List[str]] = None) -> int:
        return self.db.add_snippet(title, content, language, category, description, tags)

    def update(self, snippet_id: int, **kwargs):
        self.db.update_snippet(snippet_id, **kwargs)

    def delete(self, snippet_id: int):
        self.db.delete_snippet(snippet_id)

    def get_all(self, category: Optional[str] = None, keyword: str = "") -> List[Dict]:
        return self.db.list_snippets(category, keyword)

    def get_categories(self) -> List[str]:
        return self.db.list_snippet_categories()

    def search(self, keyword: str) -> List[Dict]:
        return self.db.list_snippets(keyword=keyword)

    def get_by_language(self, language: str) -> List[Dict]:
        all_snippets = self.db.list_snippets()
        return [s for s in all_snippets if s.get("language", "").lower() == language.lower()]

    def duplicate(self, snippet_id: int) -> int:
        snippets = self.db.list_snippets()
        for s in snippets:
            if s["id"] == snippet_id:
                return self.add(
                    title=f"{s['title']} (副本)",
                    content=s["content"],
                    language=s.get("language", ""),
                    category=s.get("category", "默认"),
                    description=s.get("description", ""),
                    tags=s.get("tags", []),
                )
        return 0
