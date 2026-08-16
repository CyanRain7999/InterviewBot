# -*- coding: utf-8 -*-
"""
Whisper 常驻子进程入口。

主程序通过 stdin 发送一行 JSON：
  {"cmd": "transcribe", "audio": "C:/xxx/recorded_audio.wav"}

子进程通过 stdout 返回一行 JSON：
  {"err_no": 0, "err_msg": "success.", "result": ["..."]}

日志全部写 stderr，避免污染 stdout。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path


def print_json(obj: dict) -> None:
    # ensure_ascii=True 避免 Windows stdout 编码导致中文乱码
    print(json.dumps(obj, ensure_ascii=True), flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    inter_dir = Path(__file__).resolve().parents[1]
    if str(inter_dir) not in sys.path:
        sys.path.insert(0, str(inter_dir))

    with contextlib.redirect_stdout(sys.stderr):
        from chatbot.asr_whisper import whisper_speech_to_text, get_whisper_model

        # 预加载模型。后续识别不会再重复加载。
        get_whisper_model(args.model, args.device, args.compute_type)

    print_json({"err_no": 0, "err_msg": "daemon_ready", "result": []})

    while True:
        line = sys.stdin.readline()

        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
            cmd = request.get("cmd", "transcribe")

            if cmd == "exit":
                print_json({"err_no": 0, "err_msg": "daemon_exit", "result": []})
                break

            if cmd != "transcribe":
                print_json({
                    "err_no": -20,
                    "err_msg": f"未知命令：{cmd}",
                    "result": []
                })
                continue

            audio = request.get("audio", "")

            with contextlib.redirect_stdout(sys.stderr):
                result = whisper_speech_to_text(
                    audio,
                    model_name=args.model,
                    device=args.device,
                    compute_type=args.compute_type,
                )

            print_json(result)

        except Exception as e:
            print_json({
                "err_no": -999,
                "err_msg": f"Whisper daemon 处理失败：{repr(e)}",
                "result": []
            })


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_json({
            "err_no": -1000,
            "err_msg": f"Whisper daemon 崩溃：{repr(e)}",
            "result": []
        })
