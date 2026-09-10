"""文件树组件 - 显示项目文件，支持打开、右键菜单"""
import os

from PySide6.QtWidgets import (
    QTreeView, QFileSystemModel, QMenu, QMessageBox, QInputDialog,
)
from PySide6.QtCore import Qt, Signal, QDir
from PySide6.QtGui import QAction


class FileTreeWidget(QTreeView):
    """文件树"""

    file_opened = Signal(str)
    file_attach_requested = Signal(str)
    file_changed = Signal()

    def __init__(self, translator=None, parent=None):
        super().__init__(parent)
        self.tr = translator
        self.current_root: str = ""

        self.model = QFileSystemModel()
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot | QDir.Hidden)
        self.setModel(self.model)

        # 隐藏多余列
        self.hideColumn(1)
        self.hideColumn(2)
        self.hideColumn(3)

        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.doubleClicked.connect(self._on_double_clicked)

        self

    def set_root_path(self, path: str):
        """设置根目录"""
        if not path or not os.path.exists(path):
            return
        self.current_root = path
        self.model.setRootPath(path)
        self.setRootIndex(self.model.index(path))

    def _on_double_clicked(self, index):
        path = self.model.filePath(index)
        if os.path.isfile(path):
            self.file_opened.emit(path)

    def _show_context_menu(self, pos):
        index = self.indexAt(pos)
        path = self.model.filePath(index) if index.isValid() else self.current_root
        # 空白处右键时 path 等于项目根：不允许对根目录执行重命名/删除（防误删整个项目）
        is_root = bool(path) and path == self.current_root

        menu = QMenu(self)
        menu

        if os.path.isfile(path):
            action_open = QAction(self.tr.tr("打开"), self)
            action_open.triggered.connect(lambda: self.file_opened.emit(path))
            menu.addAction(action_open)

            action_copy_path = QAction(self.tr.tr("复制路径"), self)
            action_copy_path.triggered.connect(lambda: self._copy_path(path))
            menu.addAction(action_copy_path)

            action_attach = QAction(self.tr.tr("附加到对话"), self)
            action_attach.triggered.connect(lambda: self.file_attach_requested.emit(path))
            menu.addAction(action_attach)

        menu.addSeparator()

        action_new_file = QAction(self.tr.tr("新建文件"), self)
        action_new_file.triggered.connect(lambda: self._new_file(path))
        menu.addAction(action_new_file)

        action_new_folder = QAction(self.tr.tr("新建文件夹"), self)
        action_new_folder.triggered.connect(lambda: self._new_folder(path))
        menu.addAction(action_new_folder)

        if not is_root:
            menu.addSeparator()

            action_rename = QAction(self.tr.tr("重命名"), self)
            action_rename.triggered.connect(lambda: self._rename(path))
            menu.addAction(action_rename)

            action_delete = QAction(self.tr.tr("删除"), self)
            action_delete.triggered.connect(lambda: self._delete(path))
            menu.addAction(action_delete)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_path(self, path: str):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(path)

    def _new_file(self, directory: str):
        if os.path.isfile(directory):
            directory = os.path.dirname(directory)
        name, ok = QInputDialog.getText(self, self.tr.tr("新建文件"), self.tr.tr("文件名:"))
        if ok and name:
            path = os.path.join(directory, name)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("")
                self.file_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def _new_folder(self, directory: str):
        if os.path.isfile(directory):
            directory = os.path.dirname(directory)
        name, ok = QInputDialog.getText(self, self.tr.tr("新建文件夹"), self.tr.tr("文件夹名:"))
        if ok and name:
            try:
                os.makedirs(os.path.join(directory, name), exist_ok=True)
                self.file_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def _rename(self, path: str):
        old_name = os.path.basename(path)
        new_name, ok = QInputDialog.getText(self, self.tr.tr("重命名"), self.tr.tr("新名称:"), text=old_name)
        if ok and new_name and new_name != old_name:
            try:
                new_path = os.path.join(os.path.dirname(path), new_name)
                os.rename(path, new_path)
                self.file_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))

    def _delete(self, path: str):
        reply = QMessageBox.question(
            self, self.tr.tr("删除"),
            f"{self.tr.tr('确定删除')} {os.path.basename(path)}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            try:
                if os.path.isdir(path):
                    import shutil
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.file_changed.emit()
            except Exception as e:
                QMessageBox.warning(self, "错误", str(e))
