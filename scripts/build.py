"""
CodeAgent 打包脚本
使用 PyInstaller 打包为 exe，然后用 Inno Setup 生成安装包
"""
import os
import sys
import subprocess
import shutil

# 项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "CodeAgent"
VERSION = "1.0.0"

# 打包输出目录
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
SPEC_FILE = os.path.join(BUILD_DIR, f"{APP_NAME}.spec")


def clean():
    """清理旧的构建文件"""
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
    print("✓ 清理完成")


def build_exe():
    """使用 PyInstaller 打包 exe"""
    print("🔨 开始打包 exe...")

    # PyInstaller 参数
    args = [
        "pyinstaller",
        "--name", APP_NAME,
        "--windowed",  # 无控制台窗口
        "--onefile",   # 单文件
        "--clean",
        "--noconfirm",
        # 图标
        # "--icon", os.path.join(PROJECT_ROOT, "resources", "icons", "app.ico"),
        # 数据文件
        "--add-data", f"{os.path.join(PROJECT_ROOT, 'resources')};resources",
        # 隐藏导入
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "openai",
        "--hidden-import", "docker",
        "--hidden-import", "git",
        # 入口
        os.path.join(PROJECT_ROOT, "main.py"),
    ]

    result = subprocess.run(args, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("❌ exe 打包失败")
        return False

    exe_path = os.path.join(DIST_DIR, f"{APP_NAME}.exe")
    if os.path.exists(exe_path):
        print(f"✓ exe 打包完成: {exe_path}")
        return True
    print("❌ 未找到生成的 exe")
    return False


def build_installer():
    """使用 Inno Setup 生成安装包"""
    print("📦 开始生成安装包...")

    iss_file = os.path.join(PROJECT_ROOT, "scripts", "build_installer.iss")

    # 查找 Inno Setup 编译器
    iscc_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        "ISCC.exe",
    ]

    iscc = None
    for p in iscc_paths:
        if os.path.exists(p) or shutil.which(p):
            iscc = p
            break

    if not iscc:
        print("⚠️  未找到 Inno Setup (ISCC.exe)，跳过安装包生成")
        print("   请安装 Inno Setup 6: https://jrsoftware.org/isdl.php")
        return False

    result = subprocess.run([iscc, iss_file], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("❌ 安装包生成失败")
        return False

    installer_path = os.path.join(DIST_DIR, f"{APP_NAME}-Setup-v{VERSION}.exe")
    if os.path.exists(installer_path):
        print(f"✓ 安装包生成完成: {installer_path}")
        return True
    print("❌ 未找到生成的安装包")
    return False


def main():
    print(f"🚀 {APP_NAME} v{VERSION} 打包脚本")
    print("=" * 50)

    clean()

    if not build_exe():
        sys.exit(1)

    build_installer()

    print("=" * 50)
    print("✅ 打包完成！")
    print(f"   输出目录: {DIST_DIR}")


if __name__ == "__main__":
    main()
