# -*- coding: utf-8 -*-
"""
Whisper 子进程入口。

由 chatbot.utils.whisper_speech_to_text_subprocess 调用。
stdout 最后一行必须是 JSON。
为避免 Windows 子进程 stdout 编码导致中文变成 ���，这里使用 ensure_ascii=True 输出纯 ASCII JSON。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path


def main() -> None:
    # 尽量统一 stdout/stderr 编码；即使 reconfigure 不可用，ensure_ascii=True 也能兜底。
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", default="small")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    # 当前文件：
    #   inter/chatbot/asr_whisper_cli.py
    # inter 目录：
    #   parents[1]
    inter_dir = Path(__file__).resolve().parents[1]
    if str(inter_dir) not in sys.path:
        sys.path.insert(0, str(inter_dir))

    # asr_whisper 里可能有 print 日志，这里重定向到 stderr，避免污染 stdout JSON。
    with contextlib.redirect_stdout(sys.stderr):
        from chatbot.asr_whisper import whisper_speech_to_text

        result = whisper_speech_to_text(
            args.audio,
            model_name=args.model,
            device=args.device,
            compute_type=args.compute_type,
        )

    # 关键：ensure_ascii=True，stdout 只输出 ASCII，父进程 json.loads 后会自动还原中文。
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({
            "err_no": -999,
            "err_msg": f"asr_whisper_cli 崩溃：{repr(e)}",
            "result": []
        }, ensure_ascii=True))
