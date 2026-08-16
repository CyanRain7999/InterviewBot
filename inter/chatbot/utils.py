# -*- coding: utf-8 -*-
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import requests

from app_paths import CONFIG_PATH, BASE_DIR


def get_config():
    """从 config.json 中获取配置信息"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_access_token(api_key, secret_key):
    """获取百度云 access_token"""
    url = "https://aip.baidubce.com/oauth/2.0/token"
    params = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": secret_key,
    }

    try:
        response = requests.post(url, params=params, timeout=10)
        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            raise RuntimeError(f"获取百度 access_token 失败：{data}")

        return access_token

    except Exception as e:
        raise RuntimeError(f"获取百度 access_token 失败：{e}")


def audio_to_base64(audio_file_path):
    """将音频文件转换为 Base64 编码"""
    with open(audio_file_path, "rb") as f:
        audio_data = f.read()
    return base64.b64encode(audio_data).decode("utf-8")


def get_file_size(file_path):
    """获取文件大小"""
    return os.stat(file_path).st_size


def baidu_speech_to_text(wav_file_path, config):
    """百度短语音识别"""
    api_key = config["API_KEY"]
    secret_key = config["SECRET_KEY"]
    cuid = config.get("CUID", "interview-self-check-local")
    dev_pid = int(config.get("BAIDU_ASR_DEV_PID", 1537))

    wav_file_path = Path(wav_file_path)

    if not wav_file_path.exists():
        return {
            "err_no": -1,
            "err_msg": f"音频文件不存在：{wav_file_path}",
            "result": []
        }

    url = "https://vop.baidu.com/server_api"

    try:
        access_token = get_access_token(api_key, secret_key)
    except Exception as e:
        return {
            "err_no": -3,
            "err_msg": str(e),
            "result": []
        }

    speech_base64 = audio_to_base64(wav_file_path)
    file_size = get_file_size(wav_file_path)

    payload = {
        "format": "wav",
        "rate": 16000,
        "channel": 1,
        "cuid": cuid,
        "speech": speech_base64,
        "len": file_size,
        "token": access_token,
        "dev_pid": dev_pid
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload),
            timeout=20
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "err_no": -2,
            "err_msg": f"百度语音识别请求失败：{e}",
            "result": []
        }


def whisper_speech_to_text_server(wav_file_path, config):
    """请求常驻 Whisper ASR 服务"""
    wav_file_path = Path(wav_file_path).resolve()

    if not wav_file_path.exists():
        return {
            "err_no": -1,
            "err_msg": f"音频文件不存在：{wav_file_path}",
            "result": []
        }

    host = config.get("WHISPER_SERVER_HOST", "127.0.0.1")
    port = int(config.get("WHISPER_SERVER_PORT", 8765))
    url = config.get("WHISPER_SERVER_URL", f"http://{host}:{port}/asr")
    timeout = int(config.get("WHISPER_TIMEOUT", 120))

    try:
        resp = requests.post(
            url,
            json={"audio": str(wav_file_path)},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {
            "err_no": -20,
            "err_msg": (
                f"请求 Whisper 常驻服务失败：{repr(e)}。"
                f"请确认 asr_server.py 已启动，URL={url}"
            ),
            "result": []
        }


def whisper_speech_to_text_subprocess(wav_file_path, config):
    """
    用子进程调用 faster-whisper。
    兜底方案：稳定，但每次都会重新加载模型，较慢。
    """
    wav_file_path = Path(wav_file_path).resolve()

    if not wav_file_path.exists():
        return {
            "err_no": -1,
            "err_msg": f"音频文件不存在：{wav_file_path}",
            "result": []
        }

    cli_path = Path(__file__).resolve().parent / "asr_whisper_cli.py"

    if not cli_path.exists():
        return {
            "err_no": -10,
            "err_msg": f"Whisper 子进程脚本不存在：{cli_path}",
            "result": []
        }

    model_name = config.get("WHISPER_MODEL", "small")
    device = config.get("WHISPER_DEVICE", "cpu")
    compute_type = config.get("WHISPER_COMPUTE_TYPE", "int8")
    timeout = int(config.get("WHISPER_TIMEOUT", 120))

    cmd = [
        sys.executable,
        str(cli_path),
        "--audio",
        str(wav_file_path),
        "--model",
        str(model_name),
        "--device",
        str(device),
        "--compute-type",
        str(compute_type),
    ]

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if completed.returncode != 0:
            return {
                "err_no": -11,
                "err_msg": (
                    f"Whisper 子进程退出码：{completed.returncode}\n"
                    f"STDERR:\n{stderr}\n"
                    f"STDOUT:\n{stdout}"
                ),
                "result": []
            }

        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not lines:
            return {
                "err_no": -12,
                "err_msg": f"Whisper 子进程没有输出。STDERR:\n{stderr}",
                "result": []
            }

        json_line = lines[-1]

        try:
            return json.loads(json_line)
        except Exception as e:
            return {
                "err_no": -13,
                "err_msg": (
                    f"解析 Whisper 子进程输出失败：{repr(e)}\n"
                    f"STDOUT:\n{stdout}\n"
                    f"STDERR:\n{stderr}"
                ),
                "result": []
            }

    except subprocess.TimeoutExpired:
        return {
            "err_no": -14,
            "err_msg": f"Whisper 子进程超时，超过 {timeout} 秒。",
            "result": []
        }
    except Exception as e:
        return {
            "err_no": -15,
            "err_msg": f"启动 Whisper 子进程失败：{repr(e)}",
            "result": []
        }


def speech_to_text(wav_file_path):
    """统一语音识别入口：支持 baidu / whisper"""
    config = get_config()

    asr_provider = config.get("ASR_PROVIDER", "baidu").lower()

    if asr_provider == "whisper":
        run_mode = config.get("WHISPER_RUN_MODE", "server").lower()

        if run_mode == "server":
            return whisper_speech_to_text_server(wav_file_path, config)

        if run_mode == "inprocess":
            # 不推荐在 PyQt 进程内运行；只保留作调试。
            from chatbot.asr_whisper import whisper_speech_to_text

            return whisper_speech_to_text(
                wav_file_path,
                model_name=config.get("WHISPER_MODEL", "small"),
                device=config.get("WHISPER_DEVICE", "cpu"),
                compute_type=config.get("WHISPER_COMPUTE_TYPE", "int8")
            )

        return whisper_speech_to_text_subprocess(wav_file_path, config)

    return baidu_speech_to_text(wav_file_path, config)
