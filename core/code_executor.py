"""代码执行器 - 在 Docker 容器中隔离运行代码和命令"""
import os
import tempfile
import time
from typing import Dict



class CodeExecutor:
    """Docker 容器代码执行器"""

    # 各语言的运行命令模板
    RUN_COMMANDS = {
        "python": "python3 {file}",
        "python3": "python3 {file}",
        "javascript": "node {file}",
        "node": "node {file}",
        "typescript": "npx ts-node {file}",
        "ts": "npx ts-node {file}",
        "java": "javac {file} && java {classname}",
        "c": "gcc {file} -o /tmp/a.out && /tmp/a.out",
        "cpp": "g++ {file} -o /tmp/a.out && /tmp/a.out",
        "c++": "g++ {file} -o /tmp/a.out && /tmp/a.out",
        "go": "go run {file}",
        "rust": "rustc {file} -o /tmp/a.out && /tmp/a.out",
        "ruby": "ruby {file}",
        "php": "php {file}",
        "bash": "bash {file}",
        "shell": "bash {file}",
        "sh": "sh {file}",
        "powershell": "pwsh {file}",
        "lua": "lua {file}",
        "perl": "perl {file}",
        "r": "Rscript {file}",
        "swift": "swift {file}",
        "kotlin": "kotlinc {file} -include-runtime -d /tmp/a.jar && java -jar /tmp/a.jar",
        "scala": "scala {file}",
        "sql": "sqlite3 /tmp/test.db < {file}",
    }

    FILE_EXTENSIONS = {
        "python": ".py", "python3": ".py",
        "javascript": ".js", "node": ".js",
        "typescript": ".ts", "ts": ".ts",
        "java": ".java", "c": ".c", "cpp": ".cpp", "c++": ".cpp",
        "go": ".go", "rust": ".rs", "ruby": ".rb", "php": ".php",
        "bash": ".sh", "shell": ".sh", "sh": ".sh",
        "powershell": ".ps1", "lua": ".lua", "perl": ".pl",
        "r": ".R", "swift": ".swift", "kotlin": ".kt", "scala": ".scala",
        "sql": ".sql",
    }

    def __init__(self, config):
        self.config = config
        self._client = None
        self._container = None

    def _get_client(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def is_docker_available(self) -> bool:
        """检查 Docker 是否可用"""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception:
            return False

    def _ensure_image(self) -> str:
        """确保执行镜像存在，返回镜像名"""
        image = self.config.get("docker_image", "codeagent-exec:latest")
        try:
            client = self._get_client()
            client.images.get(image)
        except Exception:
            # 镜像不存在，尝试用基础镜像
            image = "python:3.11-slim"
        return image

    def run_code(self, language: str, code: str, timeout: int = 300) -> Dict:
        """
        在 Docker 容器中运行代码
        返回: {"exit_code": int, "stdout": str, "stderr": str, "duration": float, "error": str}
        """
        start = time.time()
        language = language.lower().strip()

        # 特殊处理：bash 直接运行命令（run_command 在 docker_enabled=False 时会本地回退）
        if language in ("bash", "shell", "sh", "powershell"):
            return self.run_command(code, timeout=timeout)

        # 尊重 docker_enabled 设置
        if not self.config.get("docker_enabled", True):
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Docker 代码执行已在设置中被禁用。请启用 Docker，或改用 run_command 本地命令。",
                "duration": 0,
                "error": "docker_disabled",
            }

        ext = self.FILE_EXTENSIONS.get(language, ".txt")
        run_cmd = self.RUN_COMMANDS.get(language)

        if not run_cmd:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"不支持的语言: {language}",
                "duration": 0,
                "error": f"unsupported_language:{language}",
            }

        try:
            client = self._get_client()
            image = self._ensure_image()

            # 创建临时文件写入代码
            with tempfile.NamedTemporaryFile(mode="w", suffix=ext, delete=False, encoding="utf-8") as f:
                f.write(code)
                temp_path = f.name

            try:
                filename = os.path.basename(temp_path)
                classname = os.path.splitext(filename)[0]
                command = run_cmd.format(file=f"/tmp/{filename}", classname=classname)

                # 启动容器执行
                container = client.containers.run(
                    image=image,
                    command=["bash", "-c", command],
                    volumes={temp_path: {"bind": f"/tmp/{filename}", "mode": "ro"}},
                    working_dir="/tmp",
                    detach=True,
                    mem_limit=self.config.get("docker_memory_limit", "2g"),
                    nano_cpus=int(self.config.get("docker_cpu_limit", 2)) * 1_000_000_000,
                    network_disabled=False,
                )

                try:
                    # 等待执行完成
                    try:
                        result = container.wait(timeout=timeout)
                        exit_code = result.get("StatusCode", -1)
                    except Exception:
                        exit_code = -1
                        try:
                            container.kill()
                        except Exception:
                            pass
                        stdout = ""
                        stderr = f"执行超时（{timeout}秒）"
                        return {
                            "exit_code": exit_code,
                            "stdout": stdout,
                            "stderr": stderr,
                            "duration": round(time.time() - start, 2),
                            "error": "timeout",
                        }

                    stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                    stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

                    return {
                        "exit_code": exit_code,
                        "stdout": stdout,
                        "stderr": stderr,
                        "duration": round(time.time() - start, 2),
                        "error": "",
                    }
                finally:
                    # 无论成功/超时/异常都清理容器，避免泄漏
                    try:
                        container.remove(force=True)
                    except Exception:
                        pass
            finally:
                os.unlink(temp_path)

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": round(time.time() - start, 2),
                "error": f"docker_error:{str(e)}",
            }

    def run_command(self, command: str, workdir: str = "", timeout: int = 300) -> Dict:
        """
        在 Docker 容器中运行 shell 命令
        """
        start = time.time()
        # 尊重 docker_enabled 设置：禁用时退回本地执行
        if not self.config.get("docker_enabled", True):
            return self.run_command_local(command, workdir, timeout)
        try:
            client = self._get_client()
            image = self._ensure_image()

            volumes = {}
            if workdir and os.path.exists(workdir):
                volumes[workdir] = {"bind": "/workspace", "mode": "rw"}

            container = client.containers.run(
                image=image,
                command=["bash", "-c", command],
                volumes=volumes,
                working_dir="/workspace" if volumes else "/tmp",
                detach=True,
                mem_limit=self.config.get("docker_memory_limit", "2g"),
                nano_cpus=int(self.config.get("docker_cpu_limit", 2)) * 1_000_000_000,
            )

            try:
                try:
                    result = container.wait(timeout=timeout)
                    exit_code = result.get("StatusCode", -1)
                except Exception:
                    exit_code = -1
                    try:
                        container.kill()
                    except Exception:
                        pass
                    return {
                        "exit_code": exit_code,
                        "stdout": "",
                        "stderr": f"执行超时（{timeout}秒）",
                        "duration": round(time.time() - start, 2),
                        "error": "timeout",
                    }

                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

                return {
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr,
                    "duration": round(time.time() - start, 2),
                    "error": "",
                }
            finally:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": round(time.time() - start, 2),
                "error": f"docker_error:{str(e)}",
            }

    def run_command_local(self, command: str, workdir: str = "", timeout: int = 300) -> Dict:
        """
        备用方案：在本地直接运行命令（Docker 不可用时使用）
        """
        import subprocess
        start = time.time()
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                cwd=workdir or None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate()
                exit_code = -1
                stderr = (stderr or "") + f"\n执行超时（{timeout}秒）"

            return {
                "exit_code": exit_code,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "duration": round(time.time() - start, 2),
                "error": "",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": round(time.time() - start, 2),
                "error": str(e),
            }
