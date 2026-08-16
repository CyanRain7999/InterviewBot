# -*- coding: utf-8 -*-
"""
从 javabetter.cn 的“面渣逆袭”在线页面提取面试问题标题，并导出 Excel/CSV。

建议放置路径：
  tools/extract_javabetter_questions.py

运行方式：
  python tools/extract_javabetter_questions.py

输出：
  data/javabetter_questions.xlsx
  data/javabetter_questions.csv

说明：
  1. 默认只提取问题标题，不抓取完整答案。
  2. 适合后续作为知识库“问题清单”基础。
  3. 如果后续要抓取答案，可在此脚本基础上按标题区间切正文。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag


START_URL = "https://javabetter.cn/sidebar/sanfene/nixi.html"
OUTPUT_DIR = Path("data")
OUTPUT_XLSX = OUTPUT_DIR / "javabetter_questions.xlsx"
OUTPUT_CSV = OUTPUT_DIR / "javabetter_questions.csv"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 20
REQUEST_INTERVAL_SECONDS = 0.6


@dataclass
class PageInfo:
    category: str
    url: str


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = text.replace("\u200b", "").replace("\xa0", " ")
    return text.strip()


def clean_question(text: str) -> str:
    text = normalize_text(text)

    # 去掉标题前的序号：1. / 1、/ 01. / 一、
    text = re.sub(r"^\d+\s*[\.、]\s*", "", text)
    text = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", text)

    # 去掉一些站点补充标识
    text = text.replace("（补充）", "").replace("(补充)", "")
    text = text.replace("【补充】", "")

    return normalize_text(text)


def is_question_like(text: str) -> bool:
    """判断标题是否像面试问题。"""
    text = clean_question(text)

    if not text:
        return False

    # 排除大章节标题
    bad_titles = {
        "前言",
        "一、引言",
        "二、内存管理",
        "三、垃圾收集",
        "四、JVM 调优",
        "五、类加载机制",
        "参考资料",
        "总结",
        "目录",
    }
    if text in bad_titles:
        return False

    # 明确带问号的直接收
    if "?" in text or "？" in text:
        return True

    # 面渣逆袭中很多标题没有问号，但本质是问题
    question_keywords = [
        "什么是", "说说", "讲讲", "介绍一下", "能说一下", "了解吗", "知道吗",
        "有哪些", "有哪几种", "区别", "为什么", "如何", "怎么", "什么时候",
        "能详细说一下", "用过", "做过", "聊聊", "谈谈", "解释一下",
        "原理", "流程", "过程", "机制", "模型", "架构", "生命周期",
        "如何排查", "怎么排查", "怎么办", "怎么解决", "如何解决",
    ]

    return any(keyword in text for keyword in question_keywords)


def discover_sanfene_pages() -> list[PageInfo]:
    """从面渣逆袭总页发现分类页面。"""
    html = fetch_html(START_URL)
    soup = BeautifulSoup(html, "lxml")

    pages: list[PageInfo] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        text = normalize_text(a.get_text(" ", strip=True))
        href = urljoin(START_URL, a["href"])

        parsed = urlparse(href)
        if parsed.netloc != "javabetter.cn":
            continue

        if "/sidebar/sanfene/" not in parsed.path:
            continue

        if not parsed.path.endswith(".html"):
            continue

        if parsed.path.endswith("/nixi.html"):
            continue

        # 只保留面渣逆袭分类页
        if "面渣逆袭" not in text:
            continue

        if href in seen:
            continue

        seen.add(href)

        # 清理分类名
        category = text
        category = category.replace("面渣逆袭-", "")
        category = category.replace("面渣逆袭（", "")
        category = category.replace("面试题八股文）必看", "")
        category = category.replace("）必看", "")
        category = category.replace("必看", "")
        category = category.strip(" -（）()")

        pages.append(PageInfo(category=category or text, url=href))

    return pages


def extract_questions_from_page(page: PageInfo) -> list[dict]:
    html = fetch_html(page.url)
    soup = BeautifulSoup(html, "lxml")

    rows: list[dict] = []
    order = 1

    # 主要问题多为 h3，追加追问/补充问题多为 h4
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if not isinstance(heading, Tag):
            continue

        level = heading.name
        raw_title = normalize_text(heading.get_text(" ", strip=True))
        question = clean_question(raw_title)

        if not is_question_like(question):
            continue

        anchor = heading.get("id") or ""
        source_url = page.url + (f"#{anchor}" if anchor else "")

        rows.append({
            "分类": page.category,
            "问题": question,
            "标题层级": level,
            "来源URL": source_url,
            "页内顺序": order,
            "口播短答": "",
            "详细解释": "",
            "关键词": "",
            "难度": "",
            "是否高频": "",
        })
        order += 1

    return rows


def deduplicate_rows(rows: Iterable[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for row in rows:
        key = (row["分类"], row["问题"])
        if key in seen:
            continue
        seen.add(key)
        result.append(row)

    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"正在发现分类页：{START_URL}")
    pages = discover_sanfene_pages()

    if not pages:
        raise RuntimeError("没有发现面渣逆袭分类页，可能是页面结构变化或网络问题。")

    print(f"发现 {len(pages)} 个分类页：")
    for page in pages:
        print(f"  - {page.category}: {page.url}")

    all_rows: list[dict] = []

    for page in pages:
        print(f"\n正在提取：{page.category} -> {page.url}")
        try:
            rows = extract_questions_from_page(page)
            print(f"  提取到 {len(rows)} 个问题")
            all_rows.extend(rows)
        except Exception as e:
            print(f"  提取失败：{e}")

        time.sleep(REQUEST_INTERVAL_SECONDS)

    all_rows = deduplicate_rows(all_rows)

    if not all_rows:
        raise RuntimeError("没有提取到任何问题。")

    df = pd.DataFrame(all_rows)

    # 重新排序字段
    columns = [
        "分类",
        "问题",
        "标题层级",
        "来源URL",
        "页内顺序",
        "口播短答",
        "详细解释",
        "关键词",
        "难度",
        "是否高频",
    ]
    df = df[columns]

    df.to_excel(OUTPUT_XLSX, index=False)
    df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    print("\n完成。")
    print(f"总问题数：{len(df)}")
    print(f"Excel 输出：{OUTPUT_XLSX.resolve()}")
    print(f"CSV 输出：{OUTPUT_CSV.resolve()}")


if __name__ == "__main__":
    main()
