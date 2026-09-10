"""SQLite 数据库管理 - 对话历史、项目、代码片段等持久化"""
import os
import sqlite3
import json
import threading
from typing import Dict, List, Optional


class Database:
    """SQLite 数据库封装（每个线程使用独立连接，避免共享连接并发问题）"""

    def __init__(self, data_dir: str):
        self.db_path = os.path.join(data_dir, "db", "codeagent.db")
        # 线程本地连接：每个线程各持一个，线程退出时由 Python 自动释放，
        # 避免“按线程 id 缓存连接永不回收”的句柄泄漏
        self._local = threading.local()
        self._lock = threading.Lock()

    def _create_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _connect(self) -> sqlite3.Connection:
        """获取当前线程的连接（首次使用时惰性创建并缓存到线程本地）"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            with self._lock:
                conn = getattr(self._local, "conn", None)
                if conn is None:
                    conn = self._create_connection()
                    self._local.conn = conn
        return conn

    def init(self):
        """初始化所有表"""
        conn = self._connect()
        conn.executescript("""
            -- 项目表
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT NOT NULL UNIQUE,
                is_favorite INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now')),
                last_opened_at REAL DEFAULT (strftime('%s','now'))
            );

            -- 对话表
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL DEFAULT '新对话',
                model TEXT DEFAULT '',
                is_pinned INTEGER DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
            );

            -- 对话标签表
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#60a5fa',
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            -- 对话-标签关联表
            CREATE TABLE IF NOT EXISTS conversation_tags (
                conversation_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (conversation_id, tag_id),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            -- 消息表
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                msg_type TEXT DEFAULT 'text',
                content TEXT NOT NULL DEFAULT '',
                metadata TEXT DEFAULT '{}',
                created_at REAL DEFAULT (strftime('%s','now')),
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            -- 代码片段表
            CREATE TABLE IF NOT EXISTS snippets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                language TEXT DEFAULT '',
                category TEXT DEFAULT '默认',
                content TEXT NOT NULL DEFAULT '',
                description TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                created_at REAL DEFAULT (strftime('%s','now')),
                updated_at REAL DEFAULT (strftime('%s','now'))
            );

            -- 操作日志表
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                status TEXT DEFAULT 'success',
                duration REAL DEFAULT 0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );

            -- 索引
            CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id);
            CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at DESC);
        """)
        conn.commit()

    # ============ 项目 ============
    def add_project(self, name: str, path: str) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT OR IGNORE INTO projects (name, path) VALUES (?, ?)", (name, path)
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM projects WHERE path=?", (path,)).fetchone()
        return row["id"] if row else 0

    def update_project_time(self, project_id: int):
        conn = self._connect()
        conn.execute(
            "UPDATE projects SET last_opened_at=strftime('%s','now') WHERE id=?",
            (project_id,),
        )
        conn.commit()

    def toggle_favorite(self, project_id: int, is_fav: bool):
        conn = self._connect()
        conn.execute(
            "UPDATE projects SET is_favorite=? WHERE id=?", (1 if is_fav else 0, project_id)
        )
        conn.commit()

    def list_projects(self, favorite_only: bool = False) -> List[Dict]:
        conn = self._connect()
        sql = "SELECT * FROM projects"
        if favorite_only:
            sql += " WHERE is_favorite=1"
        sql += " ORDER BY last_opened_at DESC"
        return [dict(r) for r in conn.execute(sql).fetchall()]

    def delete_project(self, project_id: int):
        conn = self._connect()
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
        conn.commit()

    # ============ 对话 ============
    def create_conversation(self, project_id: Optional[int] = None,
                             title: str = "新对话", model: str = "") -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO conversations (project_id, title, model) VALUES (?, ?, ?)",
            (project_id, title, model),
        )
        conn.commit()
        return cur.lastrowid

    def update_conversation(self, conv_id: int, **kwargs):
        if not kwargs:
            return
        conn = self._connect()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [conv_id]
        conn.execute(
            f"UPDATE conversations SET {sets}, updated_at=strftime('%s','now') WHERE id=?",
            vals,
        )
        conn.commit()

    def list_conversations(self, project_id: Optional[int] = None) -> List[Dict]:
        conn = self._connect()
        if project_id:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE project_id=? ORDER BY is_pinned DESC, updated_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY is_pinned DESC, updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_conversation(self, conv_id: int):
        conn = self._connect()
        conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        conn.commit()

    def search_conversations(self, keyword: str) -> List[Dict]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT DISTINCT c.* FROM conversations c
               LEFT JOIN messages m ON m.conversation_id=c.id
               WHERE c.title LIKE ? OR m.content LIKE ?
               ORDER BY c.updated_at DESC""",
            (f"%{keyword}%", f"%{keyword}%"),
        ).fetchall()
        return [dict(r) for r in rows]

    # ============ 消息 ============
    def add_message(self, conversation_id: int, role: str, content: str,
                    msg_type: str = "text", metadata: Optional[Dict] = None) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO messages (conversation_id, role, msg_type, content, metadata) VALUES (?, ?, ?, ?, ?)",
            (conversation_id, role, msg_type, content, json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.execute(
            "UPDATE conversations SET updated_at=strftime('%s','now') WHERE id=?",
            (conversation_id,),
        )
        conn.commit()
        return cur.lastrowid

    def list_messages(self, conversation_id: int) -> List[Dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id=? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except json.JSONDecodeError:
                d["metadata"] = {}
            result.append(d)
        return result

    # ============ 标签 ============
    def add_tag(self, name: str, color: str = "#60a5fa") -> int:
        conn = self._connect()
        cur = conn.execute("INSERT OR IGNORE INTO tags (name, color) VALUES (?, ?)", (name, color))
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()
        return row["id"] if row else 0

    def list_tags(self) -> List[Dict]:
        conn = self._connect()
        return [dict(r) for r in conn.execute("SELECT * FROM tags ORDER BY name").fetchall()]

    def tag_conversation(self, conv_id: int, tag_id: int):
        conn = self._connect()
        conn.execute(
            "INSERT OR IGNORE INTO conversation_tags (conversation_id, tag_id) VALUES (?, ?)",
            (conv_id, tag_id),
        )
        conn.commit()

    def untag_conversation(self, conv_id: int, tag_id: int):
        conn = self._connect()
        conn.execute(
            "DELETE FROM conversation_tags WHERE conversation_id=? AND tag_id=?",
            (conv_id, tag_id),
        )
        conn.commit()

    def get_conversation_tags(self, conv_id: int) -> List[Dict]:
        conn = self._connect()
        rows = conn.execute(
            """SELECT t.* FROM tags t
               JOIN conversation_tags ct ON ct.tag_id=t.id
               WHERE ct.conversation_id=?""",
            (conv_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ============ 代码片段 ============
    def add_snippet(self, title: str, content: str, language: str = "",
                     category: str = "默认", description: str = "", tags: Optional[List] = None) -> int:
        conn = self._connect()
        cur = conn.execute(
            """INSERT INTO snippets (title, content, language, category, description, tags)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, content, language, category, description, json.dumps(tags or [], ensure_ascii=False)),
        )
        conn.commit()
        return cur.lastrowid

    def update_snippet(self, snippet_id: int, **kwargs):
        if not kwargs:
            return
        conn = self._connect()
        if "tags" in kwargs and isinstance(kwargs["tags"], list):
            kwargs["tags"] = json.dumps(kwargs["tags"], ensure_ascii=False)
        sets = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [snippet_id]
        conn.execute(
            f"UPDATE snippets SET {sets}, updated_at=strftime('%s','now') WHERE id=?", vals
        )
        conn.commit()

    def list_snippets(self, category: Optional[str] = None, keyword: str = "") -> List[Dict]:
        conn = self._connect()
        sql = "SELECT * FROM snippets WHERE 1=1"
        params = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if keyword:
            sql += " AND (title LIKE ? OR content LIKE ? OR description LIKE ?)"
            kw = f"%{keyword}%"
            params.extend([kw, kw, kw])
        sql += " ORDER BY updated_at DESC"
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except json.JSONDecodeError:
                d["tags"] = []
            result.append(d)
        return result

    def delete_snippet(self, snippet_id: int):
        conn = self._connect()
        conn.execute("DELETE FROM snippets WHERE id=?", (snippet_id,))
        conn.commit()

    def list_snippet_categories(self) -> List[str]:
        conn = self._connect()
        rows = conn.execute("SELECT DISTINCT category FROM snippets ORDER BY category").fetchall()
        return [r["category"] for r in rows]

    # ============ 操作日志 ============
    def add_log(self, action: str, detail: str = "", status: str = "success", duration: float = 0):
        conn = self._connect()
        conn.execute(
            "INSERT INTO action_logs (action, detail, status, duration) VALUES (?, ?, ?, ?)",
            (action, detail, status, duration),
        )
        conn.commit()

    def list_logs(self, limit: int = 500, action: str = "") -> List[Dict]:
        conn = self._connect()
        if action:
            rows = conn.execute(
                "SELECT * FROM action_logs WHERE action=? ORDER BY id DESC LIMIT ?",
                (action, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM action_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        """关闭当前线程的连接（其他线程的连接随其线程结束自动释放）"""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            try:
                del self._local.conn
            except Exception:
                pass
