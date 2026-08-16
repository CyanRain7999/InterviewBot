# -*- coding: utf-8 -*-
"""
不生成答案，只把 javabetter 问题清单导出成当前程序可导入的“召回型知识库”。

建议放置路径：
  tools/export_javabetter_question_refs_import.py

输入：
  data/javabetter_kg_workbook.xlsx

输出：
  data/javabetter_question_refs_import.xlsx

运行：
  python tools/export_javabetter_question_refs_import.py

用途：
  这个文件用于让 KG 先“召回标准问题/分类/来源”，而不是保存完整答案。
  如果你不想批量调用 DeepSeek，也不想搬运整站答案，可以先用这个。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/javabetter_kg_workbook.xlsx")
OUTPUT_PATH = Path("data/javabetter_question_refs_import.xlsx")


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH.resolve()}")

    df = pd.read_excel(INPUT_PATH)

    for col in ["分类", "问题", "来源URL", "关键词", "难度", "是否高频"]:
        if col not in df.columns:
            df[col] = ""

    df["问题"] = df["问题"].fillna("").astype(str).str.strip()
    df = df[df["问题"] != ""].copy()

    def make_answer(row) -> str:
        category = str(row.get("分类", "") or "").strip()
        url = str(row.get("来源URL", "") or "").strip()
        keywords = str(row.get("关键词", "") or "").strip()
        difficulty = str(row.get("难度", "") or "").strip()
        high = str(row.get("是否高频", "") or "").strip()

        lines = [
            f"【分类】{category}",
            "【说明】该条目是 javabetter 面试题清单中的标准问题召回项，当前未预生成完整答案。",
        ]
        if keywords:
            lines.append(f"【关键词】{keywords}")
        if difficulty:
            lines.append(f"【难度】{difficulty}")
        if high:
            lines.append(f"【是否高频】{high}")
        if url:
            lines.append(f"【来源】{url}")

        lines.append("【建议】命中该题后，使用 AI 极速版/详细版按你的简历口播风格现场生成答案。")
        return "\n".join(lines)

    out = pd.DataFrame()
    out["问题"] = df["问题"]
    out["答案"] = df.apply(make_answer, axis=1)

    out = out.drop_duplicates(subset=["问题", "答案"], keep="first")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_excel(OUTPUT_PATH, index=False)

    print("导出完成。")
    print(f"输出文件：{OUTPUT_PATH.resolve()}")
    print(f"可导入条数：{len(out)}")


if __name__ == "__main__":
    main()
