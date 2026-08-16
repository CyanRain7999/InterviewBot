# -*- coding: utf-8 -*-
"""
Whisper persistent ASR server.

Place:
  inter/asr_server.py

Run from project root:
  .venv\Scripts\python.exe inter\asr_server.py

Or run from inter:
  ..\.venv\Scripts\python.exe asr_server.py

Endpoints:
  GET  /health
  POST /asr
       JSON: {"audio": "C:/.../recorded_audio.wav"}

Why:
  Keeps faster-whisper loaded in a separate process.
  PyQt UI will not load ctranslate2 directly, avoiding native crashes and repeated model loading delay.
"""

from __future__ import annotations

import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# Current file:
#   inter/asr_server.py
INTER_DIR = Path(__file__).resolve().parent
if str(INTER_DIR) not in sys.path:
    sys.path.insert(0, str(INTER_DIR))


def _add_nvidia_dll_paths() -> None:
    """Windows 下自动加载 pip 安装的 CUDA 运行库（cuBLAS/cuDNN），
    否则 ctranslate2 报 'cublas64_12.dll is not found'"""
    import os

    try:
        import nvidia
    except Exception:
        return

    root = nvidia.__path__[0]  # ...\site-packages\nvidia（命名空间包没有 __file__）
    for name in os.listdir(root):
        bin_dir = os.path.join(root, name, "bin")
        if os.path.isdir(bin_dir):
            try:
                os.add_dll_directory(bin_dir)
            except Exception:
                pass
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


_add_nvidia_dll_paths()

from app_paths import CONFIG_PATH
from chatbot.asr_whisper import get_whisper_model, whisper_speech_to_text


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = load_config()
HOST = CONFIG.get("WHISPER_SERVER_HOST", "127.0.0.1")
PORT = int(CONFIG.get("WHISPER_SERVER_PORT", 8765))

MODEL_NAME = CONFIG.get("WHISPER_MODEL", "small")
DEVICE = CONFIG.get("WHISPER_DEVICE", "cpu")
COMPUTE_TYPE = CONFIG.get("WHISPER_COMPUTE_TYPE", "int8")

READY = False
LAST_ERROR = ""


def json_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def preload_model() -> None:
    global READY, LAST_ERROR
    try:
        print("[ASR Server] Preloading Whisper model...", flush=True)
        print(f"[ASR Server] model={MODEL_NAME}", flush=True)
        print(f"[ASR Server] device={DEVICE}, compute_type={COMPUTE_TYPE}", flush=True)
        get_whisper_model(MODEL_NAME, DEVICE, COMPUTE_TYPE)
        READY = True
        LAST_ERROR = ""
        print("[ASR Server] Ready.", flush=True)
    except Exception as e:
        READY = False
        LAST_ERROR = repr(e)
        print("[ASR Server] Failed to preload model:", repr(e), flush=True)
        traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send_json(self, status: int, data: dict) -> None:
        body = json_bytes(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/health":
            self.send_json(200, {
                "ok": True,
                "ready": READY,
                "last_error": LAST_ERROR,
                "model": MODEL_NAME,
                "device": DEVICE,
                "compute_type": COMPUTE_TYPE,
            })
            return

        self.send_json(404, {
            "ok": False,
            "err_msg": f"Unknown endpoint: {path}"
        })

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        if path != "/asr":
            self.send_json(404, {
                "ok": False,
                "err_msg": f"Unknown endpoint: {path}"
            })
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body or "{}")

            audio = payload.get("audio", "")
            if not audio:
                self.send_json(400, {
                    "err_no": -101,
                    "err_msg": "Missing audio path.",
                    "result": []
                })
                return

            if not READY:
                self.send_json(503, {
                    "err_no": -102,
                    "err_msg": f"ASR server not ready. last_error={LAST_ERROR}",
                    "result": []
                })
                return

            print(f"[ASR Server] Transcribing: {audio}", flush=True)

            result = whisper_speech_to_text(
                audio,
                model_name=MODEL_NAME,
                device=DEVICE,
                compute_type=COMPUTE_TYPE,
            )

            self.send_json(200, result)

        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {
                "err_no": -199,
                "err_msg": f"ASR server error: {repr(e)}",
                "result": []
            })

    def log_message(self, fmt, *args):
        # Keep logs concise.
        print("[ASR Server]", fmt % args, flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    preload_model()

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"[ASR Server] Listening on http://{HOST}:{PORT}", flush=True)
    print("[ASR Server] Keep this window open while using the PyQt app.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
