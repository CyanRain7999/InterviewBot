# -*- coding: utf-8 -*-
"""
清洗 javabetter_questions.xlsx，生成待补全答案的题库表。

建议放置路径：
  tools/prepare_javabetter_kg.py

输入：
  data/javabetter_questions.xlsx

输出：
  data/javabetter_kg_workbook.xlsx

运行：
  python tools/prepare_javabetter_kg.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/javabetter_questions.xlsx")
OUTPUT_PATH = Path("data/javabetter_kg_workbook.xlsx")

# 这两个分类偏工具/项目宣传，先默认排除。需要时可以删掉。
EXCLUDE_CATEGORIES = {"OpenClaw", "Skills"}


def normalize_question(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"^\d+\s*[\.、]\s*", "", text)
    return text.strip()


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH.resolve()}")

    df = pd.read_excel(INPUT_PATH)

    required = {"分类", "问题", "来源URL"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"输入文件缺少列：{missing}")

    df["问题"] = df["问题"].map(normalize_question)
    df = df[df["问题"].notna()]
    df = df[df["问题"].str.len() > 0]

    # 排除不想进入八股题库的分类
    df = df[~df["分类"].isin(EXCLUDE_CATEGORIES)]

    # 去重：同一问题在不同分类下可能都合理，所以优先按 分类+问题 去重
    df = df.drop_duplicates(subset=["分类", "问题"], keep="first")

    # 给后续答案生成留字段
    if "口播短答" not in df.columns:
        df["口播短答"] = ""
    if "详细解释" not in df.columns:
        df["详细解释"] = ""

    if "关键词" not in df.columns:
        df["关键词"] = ""
    if "难度" not in df.columns:
        df["难度"] = ""
    if "是否高频" not in df.columns:
        df["是否高频"] = ""

    # 当前程序兼容导入列。答案先空着，等生成后再填。
    df["答案"] = ""

    columns = [
        "分类",
        "问题",
        "口播短答",
        "详细解释",
        "答案",
        "关键词",
        "难度",
        "是否高频",
        "来源URL",
        "标题层级",
        "页内顺序",
    ]
    columns = [c for c in columns if c in df.columns]
    df = df[columns]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(OUTPUT_PATH, index=False)

    print("清洗完成。")
    print(f"输出文件：{OUTPUT_PATH.resolve()}")
    print(f"题目数量：{len(df)}")
    print("下一步：运行 generate_javabetter_answers.py 分批生成口播短答和详细解释。")


if __name__ == "__main__":
    main()
