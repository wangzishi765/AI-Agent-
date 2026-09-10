"""OCR 引擎 - 截图文字识别"""
import os
from typing import Optional


class OCREngine:
    """OCR 文字识别引擎（基于 Tesseract）"""

    def __init__(self, config=None):
        self.config = config
        self._available = None

    def is_available(self) -> bool:
        """检查 OCR 是否可用"""
        if self._available is not None:
            return self._available
        try:
            import pytesseract
            # 尝试获取 tesseract 版本
            pytesseract.get_tesseract_version()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def recognize(self, image_path: str, language: str = "chi_sim+eng") -> str:
        """
        识别图片中的文字
        """
        if not self.is_available():
            return "[OCR 不可用: 请安装 Tesseract 和 pytesseract]"

        if not os.path.exists(image_path):
            return f"[OCR 错误: 文件不存在 {image_path}]"

        try:
            import pytesseract
            from PIL import Image
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang=language)
            return text.strip()
        except Exception as e:
            return f"[OCR 识别失败: {e}]"

    def recognize_from_clipboard(self) -> Optional[str]:
        """从剪贴板识别图片"""
        temp_path = None
        try:
            from PIL import Image, ImageGrab
            img = ImageGrab.grabclipboard()
            if img is None:
                return None
            # 剪贴板中可能是文件路径列表（复制文件而非图像）
            if not isinstance(img, Image.Image):
                return None
            # 保存到唯一临时文件
            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix=".png", prefix="codeagent_ocr_")
            os.close(fd)
            img.save(temp_path)
            result = self.recognize(temp_path)
            return result
        except Exception:
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
