# -*- coding: utf-8 -*-
"""
DeepSeek 版 javabetter 题库答案生成脚本：修复 pandas 空列 float64 写入失败问题。

放置路径：
  tools/generate_javabetter_answers.py

输入：
  data/javabetter_kg_workbook.xlsx
  inter/config/config.json
  inter/prompt/prompt.txt

示例：
  python tools\\generate_javabetter_answers.py --category JVM --limit 10
  python tools\\generate_javabetter_answers.py --category Java并发编程 --limit 50
  python tools\\generate_javabetter_answers.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI


WORKBOOK_PATH = Path("data/javabetter_kg_workbook.xlsx")
CONFIG_PATH = Path("inter/config/config.json")
PROMPT_PATH = Path("inter/prompt/prompt.txt")

TEXT_COLUMNS = ["口播短答", "详细解释", "答案", "关键词", "难度", "是否高频"]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件：{CONFIG_PATH.resolve()}")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_resume_prompt() -> str:
    if not PROMPT_PATH.exists():
        return ""

    with open(PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def clean_text(text) -> str:
    if text is None:
        return ""
    try:
        if pd.isna(text):
            return ""
    except Exception:
        pass
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def load_workbook_as_text() -> pd.DataFrame:
    """
    关键修复：
    1. read_excel(dtype=object)，避免空列被推断成 float64。
    2. 对需要写入字符串的列统一 fillna('').astype(object)。
    """
    df = pd.read_excel(WORKBOOK_PATH, dtype=object)

    for col in TEXT_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(object)

    return df


def parse_answer(raw: str) -> tuple[str, str, str]:
    """
    期望模型输出三段：
    口播短答：
    关键词：
    难度：
    """
    raw = str(raw or "").strip()

    def pick(name: str) -> str:
        pattern = rf"{name}[:：]\s*(.*?)(?=\n\S+[:：]|\Z)"
        m = re.search(pattern, raw, flags=re.S)
        return clean_text(m.group(1)) if m else ""

    short = pick("口播短答")
    keywords = pick("关键词")
    difficulty = pick("难度")

    if not short:
        parts = [p.strip() for p in re.split(r"\n+", raw) if p.strip()]
        short = clean_text(parts[0])[:180] if parts else raw[:180]

    if difficulty not in {"基础", "中等", "较难"}:
        difficulty = "基础"

    return short, keywords, difficulty


def build_messages(resume_prompt: str, category: str, question: str) -> list[dict]:
    system = f"""
你是一个后端开发实习面试题库生成助手。
你要根据用户的真实简历背景，生成适合他面试时直接使用的原创中文回答。
不要复制任何网站原文，不要提到你在生成题库，不要说“根据你的简历”。

简历与回答风格要求如下：
{resume_prompt}

本次输出必须严格使用以下格式：

口播短答：
这里写 80 到 150 个中文字符，必须能直接念出来。

关键词：
用逗号分隔 3 到 8 个关键词。

难度：
基础 / 中等 / 较难 三选一。
""".strip()

    user = f"分类：{category}\n问题：{question}"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def save_workbook(df: pd.DataFrame) -> None:
    for col in TEXT_COLUMNS:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(object)

    WORKBOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(WORKBOOK_PATH, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="", help="只生成某个分类，例如 JVM、MySQL、Java并发编程")
    parser.add_argument("--limit", type=int, default=20, help="本次最多生成多少条")
    parser.add_argument("--sleep", type=float, default=0.5, help="每条请求之间暂停秒数")
    parser.add_argument("--model", default="", help="覆盖 config.json 里的 MODEL_NAME，例如 deepseek-v4-flash")
    args = parser.parse_args()

    if not WORKBOOK_PATH.exists():
        raise FileNotFoundError(f"找不到工作簿：{WORKBOOK_PATH.resolve()}，请先运行 prepare_javabetter_kg.py")

    config = load_config()
    resume_prompt = load_resume_prompt()

    model_name = args.model.strip() or config.get("MODEL_NAME", "deepseek-v4-flash")

    client = OpenAI(
        api_key=config["OPENAI_API_KEY"],
        base_url=config["API_URL"],
    )

    df = load_workbook_as_text()

    if "分类" not in df.columns or "问题" not in df.columns:
        raise ValueError("工作簿必须包含“分类”和“问题”两列。")

    mask = df["口播短答"].fillna("").astype(str).str.strip().eq("")
    if args.category:
        mask &= df["分类"].fillna("").astype(str).eq(args.category)

    indices = df[mask].index.tolist()[: args.limit]

    if not indices:
        print("没有需要生成的题目。")
        return

    print(f"本次准备生成 {len(indices)} 条。")
    print(f"使用模型：{model_name}")

    for i, idx in enumerate(indices, start=1):
        category = clean_text(df.at[idx, "分类"])
        question = clean_text(df.at[idx, "问题"])

        print(f"[{i}/{len(indices)}] {category} - {question}")

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=build_messages(resume_prompt, category, question),
                temperature=0.25,
                max_tokens=600,
                timeout=60,
            )
            raw = response.choices[0].message.content or ""
            
            short, keywords, difficulty = parse_answer(raw)

            df.loc[idx, "口播短答"] = str(short)
            df.loc[idx, "详细解释"] = ""
            df.loc[idx, "答案"] = f"【口播短答】\n{short}"
            df.loc[idx, "关键词"] = str(keywords)
            df.loc[idx, "难度"] = str(difficulty)

            if not clean_text(df.loc[idx, "是否高频"]):
                high_categories = {"Java SE", "Java集合框架", "Java并发编程", "JVM", "MySQL", "Redis", "Spring", "MyBatis"}
                df.loc[idx, "是否高频"] = "是" if category in high_categories else "否"

            save_workbook(df)
            time.sleep(args.sleep)

        except KeyboardInterrupt:
            print("\n手动中断，正在保存当前进度...")
            save_workbook(df)
            raise

        except Exception as e:
            print(f"  生成失败：{e}")
            save_workbook(df)
            time.sleep(args.sleep)

    print("本批次完成。")
    print(f"已更新：{WORKBOOK_PATH.resolve()}")


if __name__ == "__main__":
    main()
