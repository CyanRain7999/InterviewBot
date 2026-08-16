# -*- coding: utf-8 -*-
"""
Whisper 常驻子进程客户端。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from app_paths import BASE_DIR


class WhisperDaemonClient:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        timeout: int = 120,
    ):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()

    def start(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return

        daemon_path = Path(__file__).resolve().parent / "asr_whisper_daemon.py"

        cmd = [
            sys.executable,
            "-u",
            str(daemon_path),
            "--model",
            str(self.model_name),
            "--device",
            str(self.device),
            "--compute-type",
            str(self.compute_type),
        ]

        self.proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        ready = self._read_json_line()
        if ready.get("err_no") != 0:
            raise RuntimeError(f"Whisper daemon 启动失败：{ready}")

    def _read_json_line(self) -> dict:
        if self.proc is None or self.proc.stdout is None:
            return {
                "err_no": -30,
                "err_msg": "Whisper daemon stdout 不存在",
                "result": []
            }

        line = self.proc.stdout.readline()

        if not line:
            stderr = self.read_stderr_tail()
            return {
                "err_no": -31,
                "err_msg": f"Whisper daemon 没有返回结果。STDERR:\\n{stderr}",
                "result": []
            }

        try:
            return json.loads(line.strip())
        except Exception as e:
            stderr = self.read_stderr_tail()
            return {
                "err_no": -32,
                "err_msg": f"Whisper daemon 输出 JSON 解析失败：{repr(e)}\\nRAW:{line}\\nSTDERR:\\n{stderr}",
                "result": []
            }

    def read_stderr_tail(self, max_chars: int = 4000) -> str:
        # 注意：不阻塞读取全部 stderr。这里只在进程已退出时读取。
        if self.proc is None or self.proc.stderr is None:
            return ""

        if self.proc.poll() is None:
            return ""

        try:
            data = self.proc.stderr.read() or ""
            return data[-max_chars:]
        except Exception:
            return ""

    def transcribe(self, audio_path: str | Path) -> dict:
        with self.lock:
            self.start()

            if self.proc is None or self.proc.stdin is None:
                return {
                    "err_no": -33,
                    "err_msg": "Whisper daemon stdin 不存在",
                    "result": []
                }

            request = {
                "cmd": "transcribe",
                "audio": str(Path(audio_path).resolve())
            }

            try:
                self.proc.stdin.write(json.dumps(request, ensure_ascii=True) + "\\n")
                self.proc.stdin.flush()
            except Exception as e:
                # 写入失败，进程可能死了。下次重启。
                self.stop()
                return {
                    "err_no": -34,
                    "err_msg": f"向 Whisper daemon 发送请求失败：{repr(e)}",
                    "result": []
                }

            result = self._read_json_line()

            if result.get("err_no") in {-31, -32, -34}:
                self.stop()

            return result

    def stop(self) -> None:
        if self.proc is None:
            return

        try:
            if self.proc.poll() is None and self.proc.stdin is not None:
                self.proc.stdin.write(json.dumps({"cmd": "exit"}) + "\\n")
                self.proc.stdin.flush()
        except Exception:
            pass

        try:
            self.proc.terminate()
        except Exception:
            pass

        self.proc = None


_daemon_client_cache: dict[tuple[str, str, str, int], WhisperDaemonClient] = {}


def get_daemon_client(
    model_name: str,
    device: str,
    compute_type: str,
    timeout: int = 120,
) -> WhisperDaemonClient:
    key = (model_name, device, compute_type, timeout)

    if key not in _daemon_client_cache:
        _daemon_client_cache[key] = WhisperDaemonClient(
            model_name=model_name,
            device=device,
            compute_type=compute_type,
            timeout=timeout,
        )

    return _daemon_client_cache[key]
