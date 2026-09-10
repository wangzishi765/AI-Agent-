"""应用常量定义"""
import os
import sys

# 项目信息
APP_NAME = "CodeAgent"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "只管代码的 AI Agent"

# 目录（PyInstaller 打包后资源位于 _MEIPASS/resources）
if getattr(sys, "frozen", False):
    _BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    PROJECT_ROOT = _BASE_DIR
else:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, "resources")
STYLES_DIR = os.path.join(RESOURCES_DIR, "styles")
ICONS_DIR = os.path.join(RESOURCES_DIR, "icons")

# 默认数据目录（用户目录下）
DEFAULT_DATA_DIR = os.path.join(os.path.expanduser("~"), ".codeagent")

# 权限模式
PERMISSION_STRICT = "strict"       # 每次操作确认
PERMISSION_SEMIAUTO = "semiauto"   # 写文件确认，运行自动
PERMISSION_FULL = "full"           # 全自动

# 模型类型
MODEL_DEEPSEEK = "deepseek"
MODEL_VLLM_LOCAL = "vllm_local"

# 对话角色
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_SYSTEM = "system"

# 消息类型
MSG_TYPE_TEXT = "text"
MSG_TYPE_CODE = "code"
MSG_TYPE_DIFF = "diff"
MSG_TYPE_FILE = "file"
MSG_TYPE_IMAGE = "image"
MSG_TYPE_TERMINAL = "terminal"
MSG_TYPE_ERROR = "error"

# 任务状态
TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_SUCCESS = "success"
TASK_FAILED = "failed"

# 支持的语言
LANGUAGES = {
    "zh_CN": "简体中文",
    "en_US": "English",
    "ja_JP": "日本語",
    "ko_KR": "한국어",
}

# 代码文件扩展名映射
CODE_EXTENSIONS = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".java": "java",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".r": "r", ".R": "r",
    ".lua": "lua",
    ".sh": "bash", ".bash": "bash",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".less": "css",
    ".vue": "vue",
    ".json": "json",
    ".yaml": "yaml", ".yml": "yaml",
    ".xml": "xml",
    ".md": "markdown",
    ".toml": "toml",
    ".ini": "ini", ".cfg": "ini",
}

# 默认快捷键
DEFAULT_SHORTCUTS = {
    "toggle_window": "Ctrl+Alt+C",
    "send_message": "Ctrl+Return",
    "new_conversation": "Ctrl+Shift+N",
    "search_files": "Ctrl+P",
    "search_code": "Ctrl+Shift+F",
    "toggle_terminal": "Ctrl+`",
    "toggle_sidebar": "Ctrl+B",
    "settings": "Ctrl+,",
    "voice_input": "Ctrl+Space",
}
