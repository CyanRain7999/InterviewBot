# -*- coding: utf-8 -*-
"""
知识库检索调试脚本。

放置路径：
  tools/debug_retriever.py

运行：
  python tools/debug_retriever.py "讲讲mysql"
  python tools/debug_retriever.py "JVM垃圾处理"
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INTER_DIR = PROJECT_ROOT / "inter"

if str(INTER_DIR) not in sys.path:
    sys.path.insert(0, str(INTER_DIR))

from chatbot.retriever import debug_search


def main():
    query = " ".join(sys.argv[1:]).strip()

    if not query:
        print('用法：python tools/debug_retriever.py "讲讲mysql"')
        return

    hits = debug_search(query, top_n=10)

    print(f"Query: {query}")
    print("=" * 80)

    for i, hit in enumerate(hits, 1):
        print(f"{i}. score={hit.score:.2f} reason={hit.reason}")
        print(f"   Q: {hit.question}")
        print()


if __name__ == "__main__":
    main()
