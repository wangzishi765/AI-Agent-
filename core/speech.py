"""语音识别器 - 按住说话，语音转文字"""
import threading
from typing import Callable, Optional


class SpeechRecognizer:
    """语音识别器（基于 SpeechRecognition + PyAudio）"""

    def __init__(self, config=None):
        self.config = config
        self._recognizer = None
        self._mic = None
        self._is_listening = False
        self._stop_event = threading.Event()
        self._available = None

    def is_available(self) -> bool:
        """检查语音识别是否可用"""
        if self._available is not None:
            return self._available
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            # 检查麦克风
            with sr.Microphone():
                pass
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def listen_once(self, language: str = "zh-CN", timeout: int = 10,
                    phrase_time_limit: int = 30) -> str:
        """
        听一次并识别
        返回识别到的文字，失败返回空字符串
        """
        if not self.is_available():
            return ""

        import speech_recognition as sr

        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_time_limit
                )

            # 使用 Google 免费识别（也可以用其他引擎）
            try:
                text = self._recognizer.recognize_google(audio, language=language)
                return text
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                return f"[语音服务错误: {e}]"

        except Exception:
            return ""

    def start_listening(self, on_result: Callable[[str], None],
                        on_error: Optional[Callable[[str], None]] = None,
                        language: str = "zh-CN"):
        """
        开始持续监听（在后台线程）
        """
        if self._is_listening:
            return

        self._is_listening = True
        self._stop_event.clear()

        def _listen_thread():
            import speech_recognition as sr
            try:
                with sr.Microphone() as source:
                    self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    while not self._stop_event.is_set():
                        try:
                            audio = self._recognizer.listen(
                                source, timeout=5, phrase_time_limit=30
                            )
                            text = self._recognizer.recognize_google(audio, language=language)
                            if text and on_result:
                                on_result(text)
                        except sr.WaitTimeoutError:
                            continue
                        except sr.UnknownValueError:
                            continue
                        except Exception as e:
                            if on_error:
                                on_error(str(e))
                            break
            except Exception as e:
                if on_error:
                    on_error(str(e))
            finally:
                self._is_listening = False

        thread = threading.Thread(target=_listen_thread, daemon=True)
        thread.start()

    def stop_listening(self):
        """
        停止监听。

        注意：只置停止标志。当前阻塞在 listen() 的线程最多还需要
        timeout 秒才会退出，_is_listening 由该线程的 finally 收尾清空，
        避免出现“快速松开再按下”时标志被提前清掉导致双线程抢麦克风。
        """
        self._stop_event.set()
