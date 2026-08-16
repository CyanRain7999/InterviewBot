# -*- coding: utf-8 -*-
"""
把补全后的 javabetter_kg_workbook.xlsx 导出成当前 UI 可导入的知识库 Excel。

建议放置路径：
  tools/export_javabetter_kg_import.py

输入：
  data/javabetter_kg_workbook.xlsx

输出：
  data/javabetter_kg_import.xlsx

运行：
  python tools/export_javabetter_kg_import.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


INPUT_PATH = Path("data/javabetter_kg_workbook.xlsx")
OUTPUT_PATH = Path("data/javabetter_kg_import.xlsx")


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"找不到输入文件：{INPUT_PATH.resolve()}")

    df = pd.read_excel(INPUT_PATH)

    required = {"问题", "答案"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"输入文件缺少列：{missing}")

    df["问题"] = df["问题"].fillna("").astype(str).str.strip()
    df["答案"] = df["答案"].fillna("").astype(str).str.strip()

    df = df[(df["问题"] != "") & (df["答案"] != "")]
    df = df.drop_duplicates(subset=["问题", "答案"], keep="first")

    out = df[["问题", "答案"]].copy()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_excel(OUTPUT_PATH, index=False)

    print("导出完成。")
    print(f"输出文件：{OUTPUT_PATH.resolve()}")
    print(f"可导入条数：{len(out)}")


if __name__ == "__main__":
    main()
