"""
设置对话框 - 包含通用、模型、代理、权限、快捷键、语音、OCR、更新等设置页
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget,
    QWidget, QLabel, QLineEdit, QComboBox, QCheckBox, QPushButton,
    QSpinBox, QDoubleSpinBox, QGroupBox, QFormLayout,
    QKeySequenceEdit, QMessageBox,
)
from PySide6.QtCore import Signal
from PySide6.QtGui import QKeySequence

from app.constants import LANGUAGES, DEFAULT_SHORTCUTS, APP_VERSION


class SettingsDialog(QDialog):
    """设置对话框"""

    settings_changed = Signal(dict)
    update_check_done = Signal(str)  # 提示文本

    def __init__(self, config, translator, parent=None):
        super().__init__(parent)
        self.config = config
        self.tr = translator
        self.setWindowTitle(self.tr.tr("设置"))
        self.setMinimumSize(800, 600)
        self._init_ui()
        self.update_check_done.connect(self._on_update_check_done)
        self._load_settings()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 左侧分类列表
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(160)
        self.category_list
        categories = [
            self.tr.tr("通用"),
            self.tr.tr("AI 模型"),
            self.tr.tr("代理"),
            self.tr.tr("权限"),
            self.tr.tr("代码执行"),
            self.tr.tr("快捷键"),
            self.tr.tr("语音 / OCR"),
            self.tr.tr("更新"),
        ]
        self.category_list.addItems(categories)
        self.category_list.setCurrentRow(0)
        layout.addWidget(self.category_list)

        # 右侧设置页
        self.stacked = QStackedWidget()
        self.stacked.setStyleSheet("background: transparent;")
        layout.addWidget(self.stacked, 1)

        self.category_list.currentRowChanged.connect(self.stacked.setCurrentIndex)

        # 创建设置页
        self._create_general_page()
        self._create_model_page()
        self._create_proxy_page()
        self._create_permission_page()
        self._create_execution_page()
        self._create_shortcuts_page()
        self._create_voice_page()
        self._create_update_page()

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_reset = QPushButton(self.tr.tr("恢复默认"))
        self.btn_reset.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(self.btn_reset)

        self.btn_cancel = QPushButton(self.tr.tr("取消"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(self.tr.tr("保存"))
        self.btn_save.setObjectName("primaryBtn")
        self.btn_save.clicked.connect(self._save_settings)
        btn_layout.addWidget(self.btn_save)

        bottom = QWidget()
        bottom.setLayout(btn_layout)
        bottom.setStyleSheet("background: transparent; padding: 10px;")

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.stacked, 1)
        main_layout.addWidget(bottom)

        # 重新布局
        central = QWidget()
        central.setLayout(main_layout)
        layout.addWidget(central, 1)

    def _create_general_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        form.addRow(self.tr.tr("界面语言") + ":", self.lang_combo)

        self.theme_combo = QComboBox()
        from app.theme import THEME_LABELS
        for code, label in THEME_LABELS.items():
            self.theme_combo.addItem(self.tr.tr(label), code)
        form.addRow(self.tr.tr("主题") + ":", self.theme_combo)

        self.close_tray_check = QCheckBox(self.tr.tr("关闭时最小化到系统托盘"))
        form.addRow("", self.close_tray_check)

        self.auto_start_check = QCheckBox(self.tr.tr("开机自启"))
        form.addRow("", self.auto_start_check)

        self.show_diff_check = QCheckBox(self.tr.tr("改文件后显示 Diff 对比"))
        form.addRow("", self.show_diff_check)

        self.auto_format_check = QCheckBox(self.tr.tr("改文件后自动格式化"))
        form.addRow("", self.auto_format_check)

        self.auto_lint_check = QCheckBox(self.tr.tr("改文件后自动运行 Linter"))
        form.addRow("", self.auto_lint_check)

        self.stacked.addWidget(page)

    def _create_model_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.active_model_combo = QComboBox()
        self.active_model_combo.addItems(["DeepSeek", "vLLM 本地"])
        form.addRow(self.tr.tr("当前模型") + ":", self.active_model_combo)

        # DeepSeek 设置
        ds_group = QGroupBox("DeepSeek API")
        ds_form = QFormLayout(ds_group)
        self.ds_api_key = QLineEdit()
        self.ds_api_key.setEchoMode(QLineEdit.Password)
        ds_form.addRow("API Key:", self.ds_api_key)
        self.ds_api_base = QLineEdit()
        ds_form.addRow("API Base:", self.ds_api_base)
        self.ds_model = QLineEdit()
        ds_form.addRow(self.tr.tr("模型名") + ":", self.ds_model)
        self.ds_temp = QDoubleSpinBox()
        self.ds_temp.setRange(0, 2)
        self.ds_temp.setSingleStep(0.1)
        ds_form.addRow("Temperature:", self.ds_temp)
        self.ds_max_tokens = QSpinBox()
        self.ds_max_tokens.setRange(256, 32768)
        ds_form.addRow("Max Tokens:", self.ds_max_tokens)
        form.addRow(ds_group)

        # vLLM 设置
        vllm_group = QGroupBox("vLLM 本地模型")
        vllm_form = QFormLayout(vllm_group)
        self.vllm_api_key = QLineEdit()
        self.vllm_api_key.setEchoMode(QLineEdit.Password)
        vllm_form.addRow("API Key:", self.vllm_api_key)
        self.vllm_api_base = QLineEdit()
        vllm_form.addRow("API Base:", self.vllm_api_base)
        self.vllm_model = QLineEdit()
        vllm_form.addRow(self.tr.tr("模型名") + ":", self.vllm_model)
        self.vllm_temp = QDoubleSpinBox()
        self.vllm_temp.setRange(0, 2)
        self.vllm_temp.setSingleStep(0.1)
        vllm_form.addRow("Temperature:", self.vllm_temp)
        self.vllm_max_tokens = QSpinBox()
        self.vllm_max_tokens.setRange(256, 32768)
        vllm_form.addRow("Max Tokens:", self.vllm_max_tokens)
        form.addRow(vllm_group)

        self.stacked.addWidget(page)

    def _create_proxy_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.proxy_enabled = QCheckBox(self.tr.tr("启用代理"))
        form.addRow("", self.proxy_enabled)

        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["HTTP", "HTTPS", "SOCKS5", self.tr.tr("系统代理")])
        form.addRow(self.tr.tr("代理类型") + ":", self.proxy_type)

        self.proxy_host = QLineEdit()
        form.addRow(self.tr.tr("主机") + ":", self.proxy_host)

        self.proxy_port = QLineEdit()
        form.addRow(self.tr.tr("端口") + ":", self.proxy_port)

        self.proxy_user = QLineEdit()
        form.addRow(self.tr.tr("用户名") + ":", self.proxy_user)

        self.proxy_pass = QLineEdit()
        self.proxy_pass.setEchoMode(QLineEdit.Password)
        form.addRow(self.tr.tr("密码") + ":", self.proxy_pass)

        btn_test = QPushButton(self.tr.tr("测试连接"))
        btn_test.clicked.connect(self._test_proxy)
        form.addRow("", btn_test)

        self.stacked.addWidget(page)

    def _create_permission_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.permission_combo = QComboBox()
        self.permission_combo.addItems([
            self.tr.tr("严格模式") + " - " + self.tr.tr("每次操作都确认"),
            self.tr.tr("半自动") + " - " + self.tr.tr("写文件确认，运行自动"),
            self.tr.tr("全自动") + " - " + self.tr.tr("全部自动执行"),
        ])
        form.addRow(self.tr.tr("权限模式") + ":", self.permission_combo)

        info = QLabel(self.tr.tr("权限模式控制 Agent 操作文件和运行代码时是否需要你的确认。"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #6b7280; font-size: 12px;")
        form.addRow("", info)

        self.stacked.addWidget(page)

    def _create_execution_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.docker_enabled = QCheckBox(self.tr.tr("使用 Docker 容器隔离运行代码"))
        form.addRow("", self.docker_enabled)

        self.docker_image = QLineEdit()
        form.addRow(self.tr.tr("Docker 镜像") + ":", self.docker_image)

        self.docker_timeout = QSpinBox()
        self.docker_timeout.setRange(10, 3600)
        self.docker_timeout.setSuffix(" s")
        form.addRow(self.tr.tr("执行超时") + ":", self.docker_timeout)

        self.docker_memory = QLineEdit()
        form.addRow(self.tr.tr("内存限制") + ":", self.docker_memory)

        self.docker_cpu = QSpinBox()
        self.docker_cpu.setRange(1, 16)
        form.addRow(self.tr.tr("CPU 限制") + ":", self.docker_cpu)

        self.stacked.addWidget(page)

    def _create_shortcuts_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.shortcut_edits = {}
        shortcut_labels = {
            "toggle_window": self.tr.tr("召唤窗口"),
            "send_message": self.tr.tr("发送消息"),
            "new_conversation": self.tr.tr("新建对话"),
            "search_files": self.tr.tr("搜索文件"),
            "search_code": self.tr.tr("搜索代码"),
            "toggle_terminal": self.tr.tr("显示/隐藏终端"),
            "toggle_sidebar": self.tr.tr("显示/隐藏侧边栏"),
            "settings": self.tr.tr("打开设置"),
            "voice_input": self.tr.tr("语音输入"),
        }
        for key, label in shortcut_labels.items():
            edit = QKeySequenceEdit()
            self.shortcut_edits[key] = edit
            form.addRow(label + ":", edit)

        btn_reset = QPushButton(self.tr.tr("恢复默认快捷键"))
        btn_reset.clicked.connect(self._reset_shortcuts)
        form.addRow("", btn_reset)

        self.stacked.addWidget(page)

    def _create_voice_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.voice_enabled = QCheckBox(self.tr.tr("启用语音输入"))
        form.addRow("", self.voice_enabled)

        self.voice_lang = QComboBox()
        self.voice_lang.addItem("中文 (zh-CN)", "zh-CN")
        self.voice_lang.addItem("English (en-US)", "en-US")
        self.voice_lang.addItem("日本語 (ja-JP)", "ja-JP")
        self.voice_lang.addItem("한국어 (ko-KR)", "ko-KR")
        form.addRow(self.tr.tr("语音语言") + ":", self.voice_lang)

        form.addRow(QLabel(""))  # 分隔

        self.ocr_enabled = QCheckBox(self.tr.tr("启用截图 OCR 识别"))
        form.addRow("", self.ocr_enabled)

        self.ocr_lang = QLineEdit()
        form.addRow("OCR " + self.tr.tr("语言") + ":", self.ocr_lang)

        info = QLabel(self.tr.tr("OCR 需要安装 Tesseract。语音输入需要 PyAudio 和 SpeechRecognition。"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #6b7280; font-size: 12px;")
        form.addRow("", info)

        self.stacked.addWidget(page)

    def _create_update_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(24, 24, 24, 24)
        form.setSpacing(12)

        self.auto_update_check = QCheckBox(self.tr.tr("启动时自动检查更新"))
        form.addRow("", self.auto_update_check)

        version_label = QLabel(f"{self.tr.tr('当前版本')}: v{APP_VERSION}")
        version_label.setStyleSheet("color: #4e6ef2; font-size: 14px; font-weight: bold;")
        form.addRow("", version_label)

        btn_check = QPushButton(self.tr.tr("立即检查更新"))
        btn_check.clicked.connect(self._check_update)
        form.addRow("", btn_check)

        self.update_info = QLabel("")
        self.update_info.setWordWrap(True)
        form.addRow("", self.update_info)

        self.stacked.addWidget(page)

    def _load_settings(self):
        """加载设置到界面"""
        # 通用
        lang = self.config.get("language", "zh_CN")
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        theme = self.config.get("theme", "tech_dark")
        theme_idx = self.theme_combo.findData(theme)
        if theme_idx < 0:
            theme_idx = self.theme_combo.findData("tech_dark")  # 旧值(如 light)回退
        if theme_idx >= 0:
            self.theme_combo.setCurrentIndex(theme_idx)
        self.close_tray_check.setChecked(self.config.get("close_to_tray", True))
        self.auto_start_check.setChecked(self.config.get("auto_start", False))
        self.show_diff_check.setChecked(self.config.get("show_diff_preview", True))
        self.auto_format_check.setChecked(self.config.get("auto_format", True))
        self.auto_lint_check.setChecked(self.config.get("auto_lint", True))

        # 模型
        model = self.config.get("active_model", "deepseek")
        self.active_model_combo.setCurrentIndex(0 if model == "deepseek" else 1)
        self.ds_api_key.setText(self.config.get("deepseek_api_key", ""))
        self.ds_api_base.setText(self.config.get("deepseek_api_base", ""))
        self.ds_model.setText(self.config.get("deepseek_model", ""))
        self.ds_temp.setValue(self.config.get("deepseek_temperature", 0.7))
        self.ds_max_tokens.setValue(self.config.get("deepseek_max_tokens", 4096))
        self.vllm_api_key.setText(self.config.get("vllm_api_key", "EMPTY"))
        self.vllm_api_base.setText(self.config.get("vllm_api_base", ""))
        self.vllm_model.setText(self.config.get("vllm_model", ""))
        self.vllm_temp.setValue(self.config.get("vllm_temperature", 0.7))
        self.vllm_max_tokens.setValue(self.config.get("vllm_max_tokens", 4096))

        # 代理
        self.proxy_enabled.setChecked(self.config.get("proxy_enabled", False))
        ptype = self.config.get("proxy_type", "http")
        ptype_idx = {"http": 0, "https": 1, "socks5": 2, "system": 3}.get(ptype, 0)
        self.proxy_type.setCurrentIndex(ptype_idx)
        self.proxy_host.setText(self.config.get("proxy_host", ""))
        self.proxy_port.setText(self.config.get("proxy_port", ""))
        self.proxy_user.setText(self.config.get("proxy_username", ""))
        self.proxy_pass.setText(self.config.get("proxy_password", ""))

        # 权限
        perm = self.config.get("permission_mode", "full")
        perm_idx = {"strict": 0, "semiauto": 1, "full": 2}.get(perm, 2)
        self.permission_combo.setCurrentIndex(perm_idx)

        # 执行
        self.docker_enabled.setChecked(self.config.get("docker_enabled", True))
        self.docker_image.setText(self.config.get("docker_image", ""))
        self.docker_timeout.setValue(self.config.get("docker_timeout", 300))
        self.docker_memory.setText(self.config.get("docker_memory_limit", "2g"))
        self.docker_cpu.setValue(self.config.get("docker_cpu_limit", 2))

        # 快捷键
        shortcuts = self.config.get("shortcuts", DEFAULT_SHORTCUTS)
        for key, edit in self.shortcut_edits.items():
            edit.setKeySequence(QKeySequence(shortcuts.get(key, "")))

        # 语音/OCR
        self.voice_enabled.setChecked(self.config.get("voice_enabled", True))
        voice_lang = self.config.get("voice_language", "zh-CN")
        idx = self.voice_lang.findData(voice_lang)
        if idx >= 0:
            self.voice_lang.setCurrentIndex(idx)
        self.ocr_enabled.setChecked(self.config.get("ocr_enabled", True))
        self.ocr_lang.setText(self.config.get("ocr_language", "chi_sim+eng"))

        # 更新
        self.auto_update_check.setChecked(self.config.get("auto_check_update", True))

    def _save_settings(self):
        """保存设置"""
        updates = {}

        # 通用
        updates["language"] = self.lang_combo.currentData()
        updates["theme"] = self.theme_combo.currentData() or "tech_dark"
        updates["close_to_tray"] = self.close_tray_check.isChecked()
        updates["auto_start"] = self.auto_start_check.isChecked()
        updates["show_diff_preview"] = self.show_diff_check.isChecked()
        updates["auto_format"] = self.auto_format_check.isChecked()
        updates["auto_lint"] = self.auto_lint_check.isChecked()

        # 模型
        updates["active_model"] = "deepseek" if self.active_model_combo.currentIndex() == 0 else "vllm_local"
        updates["deepseek_api_key"] = self.ds_api_key.text()
        updates["deepseek_api_base"] = self.ds_api_base.text()
        updates["deepseek_model"] = self.ds_model.text()
        updates["deepseek_temperature"] = self.ds_temp.value()
        updates["deepseek_max_tokens"] = self.ds_max_tokens.value()
        updates["vllm_api_key"] = self.vllm_api_key.text()
        updates["vllm_api_base"] = self.vllm_api_base.text()
        updates["vllm_model"] = self.vllm_model.text()
        updates["vllm_temperature"] = self.vllm_temp.value()
        updates["vllm_max_tokens"] = self.vllm_max_tokens.value()

        # 代理
        updates["proxy_enabled"] = self.proxy_enabled.isChecked()
        updates["proxy_type"] = ["http", "https", "socks5", "system"][self.proxy_type.currentIndex()]
        updates["proxy_host"] = self.proxy_host.text()
        updates["proxy_port"] = self.proxy_port.text()
        updates["proxy_username"] = self.proxy_user.text()
        updates["proxy_password"] = self.proxy_pass.text()

        # 权限
        updates["permission_mode"] = ["strict", "semiauto", "full"][self.permission_combo.currentIndex()]

        # 执行
        updates["docker_enabled"] = self.docker_enabled.isChecked()
        updates["docker_image"] = self.docker_image.text()
        updates["docker_timeout"] = self.docker_timeout.value()
        updates["docker_memory_limit"] = self.docker_memory.text()
        updates["docker_cpu_limit"] = self.docker_cpu.value()

        # 快捷键
        shortcuts = {}
        for key, edit in self.shortcut_edits.items():
            shortcuts[key] = edit.keySequence().toString()
        updates["shortcuts"] = shortcuts

        # 语音/OCR
        updates["voice_enabled"] = self.voice_enabled.isChecked()
        updates["voice_language"] = self.voice_lang.currentData() or "zh-CN"
        updates["ocr_enabled"] = self.ocr_enabled.isChecked()
        updates["ocr_language"] = self.ocr_lang.text()

        # 更新
        updates["auto_check_update"] = self.auto_update_check.isChecked()

        self.config.update(updates)
        self.settings_changed.emit(updates)
        self.accept()

    def _reset_defaults(self):
        reply = QMessageBox.question(
            self, self.tr.tr("恢复默认"),
            self.tr.tr("确定恢复所有设置为默认值吗？"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.config.reset()
            self._load_settings()

    def _reset_shortcuts(self):
        for key, edit in self.shortcut_edits.items():
            edit.setKeySequence(QKeySequence(DEFAULT_SHORTCUTS.get(key, "")))

    def _test_proxy(self):
        QMessageBox.information(self, self.tr.tr("代理测试"), self.tr.tr("代理连接测试功能（需配置后测试）"))

    def _check_update(self):
        import threading
        self.update_info.setText(self.tr.tr("正在检查更新..."))
        try:
            from app.updater import Updater
            updater = Updater(self.config)
        except Exception as e:
            self.update_info.setText(str(e))
            return

        def worker():
            try:
                has_update, latest, _info = updater.check_for_updates()
            except Exception as e:
                self.update_check_done.emit(f"{self.tr.tr('检查更新失败')}: {e}")
                return
            if has_update:
                text = f"{self.tr.tr('发现新版本')}: v{latest}"
            else:
                text = self.tr.tr("当前已是最新版本")
            self.update_check_done.emit(text)

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_check_done(self, text: str):
        self.update_info.setText(text)
