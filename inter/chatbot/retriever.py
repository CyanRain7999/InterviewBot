# -*- coding: utf-8 -*-
"""
轻量级知识库检索器。

放置路径：
  inter/chatbot/retriever.py

目标：
  替代原先 jieba + SQLite LIKE 的粗糙检索。
  对 1000~5000 条面试题库，直接全表扫描打分就足够快。

特性：
  1. 支持中英混合技术词归一化：JMV -> JVM, jvm garbage -> JVM 垃圾回收。
  2. 支持 fuzzy 匹配；如果安装 rapidfuzz，会自动使用 rapidfuzz。
  3. 对 MySQL / Redis / JVM / Spring 等核心技术词做强约束，避免“讲讲 MySQL”召回 JVM。
  4. 保持返回格式 [(question, answer), ...]，兼容当前 ui.py。
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from difflib import SequenceMatcher

import jieba

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

try:
    from chatbot.text_normalizer import normalize_interview_text
except Exception:
    def normalize_interview_text(text: str) -> str:
        return text or ""

from app_paths import KNOWLEDGE_DB_PATH


TECH_TERMS = [
    "mysql", "redis", "spring boot", "spring", "jvm", "gc", "tlab", "cas", "aqs",
    "jmm", "mvcc", "innodb", "b+tree", "btree", "hashmap", "concurrenthashmap",
    "threadlocal", "mybatis", "rocketmq", "http", "https", "tcp", "udp", "sql",
    "java", "golang", "linux"
]

STOPWORDS = {
    "讲讲", "说说", "介绍", "介绍一下", "一下", "什么是", "什么", "怎么", "如何",
    "为什么", "说一下", "聊聊", "谈谈", "请", "的", "了", "吗", "呢", "啊",
    "和", "与", "以及", "一个", "一下子", "能不能", "能", "不能",
    "哪些", "哪几种", "哪几", "几个", "有哪些",
}

SYNONYM_REPLACEMENTS = {
    "jmv": "jvm",
    "j m v": "jvm",
    "java虚拟机": "jvm",
    "垃圾处理": "垃圾回收",
    "垃圾清理": "垃圾回收",
    "垃圾管理": "垃圾回收",
    "所引": "索引",
    "锁引": "索引",
    "买色口": "mysql",
    "麦色口": "mysql",
    "麦涩口": "mysql",
    "买涩口": "mysql",
    "master code": "mysql",
    "master口": "mysql",
    "瑞迪斯": "redis",
    "雷迪斯": "redis",
    "斯普林布特": "spring boot",
    "斯普林": "spring",
    "哈西麦普": "hashmap",
    "哈希麦普": "hashmap",
    "哈西玛普": "hashmap",
    "哈希玛普": "hashmap",
    "哈西特保": "hashtable",
    "哈希表": "hashmap",
}


@dataclass
class SearchHit:
    question: str
    answer: str
    score: float
    reason: str = ""


def normalize_for_search(text: str) -> str:
    text = normalize_interview_text(text or "")
    text = text.lower()
    text = text.replace("＋", "+")
    text = re.sub(r"[🌟⭐🔥✅❌【】\[\]（）()《》“”\"'`]", " ", text)

    for src, dst in SYNONYM_REPLACEMENTS.items():
        text = text.replace(src.lower(), dst.lower())

    # 常见写法归一
    text = re.sub(r"\bmy\s+sql\b", "mysql", text)
    text = re.sub(r"\bspring\s*boot\b", "spring boot", text)
    text = re.sub(r"\bb\s*\+\s*tree\b", "b+tree", text)

    text = re.sub(r"\s+", " ", text).strip()
    return text


def compact(text: str) -> str:
    """去掉空白和常见标点，方便中文短句相似度比较"""
    text = normalize_for_search(text)
    return re.sub(r"[\s,，。？?！!：:；;、/\-_]+", "", text)


def tokenize(text: str) -> list[str]:
    text = normalize_for_search(text)

    tokens: list[str] = []

    # 先抓英文/数字/技术符号词
    for m in re.finditer(r"[a-zA-Z][a-zA-Z0-9+#.\-]*", text):
        token = m.group(0).lower().strip()
        if token and token not in STOPWORDS:
            tokens.append(token)

    # 再用 jieba 切中文
    for token in jieba.cut(text):
        token = token.strip().lower()
        if not token or token in STOPWORDS:
            continue
        if len(token) == 1 and not re.match(r"[a-z0-9]", token):
            continue
        tokens.append(token)

    # 合并技术词
    joined = " ".join(tokens)
    if "spring" in joined and "boot" in joined:
        tokens.append("spring boot")

    # 去重保序
    seen = set()
    result = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def extract_core_terms(text: str) -> set[str]:
    norm = normalize_for_search(text)
    cores = set()

    for term in TECH_TERMS:
        if term in norm:
            cores.add(term)

    # 特殊：gc 与 垃圾回收
    if "垃圾回收" in norm:
        cores.add("gc")

    return cores


def fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0

    if fuzz is not None:
        return float(fuzz.WRatio(a, b))

    return SequenceMatcher(None, a, b).ratio() * 100


def token_overlap_score(query_tokens: list[str], target_tokens: list[str]) -> float:
    if not query_tokens or not target_tokens:
        return 0.0

    q = set(query_tokens)
    t = set(target_tokens)

    inter = q & t

    # 子串匹配：查询里的短词（如“锁”）应能命中题库里的复合词（如“锁升级”），
    # 弥补 jieba 分词粒度不一致导致的漏匹配
    for qt in q:
        if qt in inter:
            continue
        if len(qt) <= 2:
            for tt in t:
                if qt in tt or tt in qt:
                    inter.add(qt)
                    break

    if not inter:
        return 0.0

    # 对查询词召回更敏感：命中多少查询词比 Jaccard 更重要
    recall = len(inter) / max(len(q), 1)
    precision = len(inter) / max(len(t), 1)

    return (recall * 0.75 + precision * 0.25) * 100


def score_row(query: str, question: str, answer: str) -> SearchHit:
    q_norm = normalize_for_search(query)
    question_norm = normalize_for_search(question)
    answer_norm = normalize_for_search(answer)

    q_compact = compact(q_norm)
    question_compact = compact(question_norm)

    q_tokens = tokenize(q_norm)
    question_tokens = tokenize(question_norm)
    answer_tokens = tokenize(answer_norm)

    q_core_terms = extract_core_terms(q_norm)
    # 核心词门控：优先只看问题标题，避免“答案顺带提到某词”的题被顶上
    row_core_terms = extract_core_terms(question_norm)
    row_core_terms_all = extract_core_terms(question_norm + " " + answer_norm)

    # 答案正文中核心词出现次数：区分“顺带提一句”（Redis 噪音）与
    # “答案主体就是这个主题”（如题目没写 MySQL 的 MySQL 题）
    answer_mentions = 0
    for term in q_core_terms:
        answer_mentions += answer_norm.lower().count(term)

    # 如果查询里有明确核心技术词，候选完全不含这个核心词，要强烈降权。
    core_gate_penalty = 0.0
    if q_core_terms and not (q_core_terms & row_core_terms):
        if answer_mentions > 0:
            core_gate_penalty = max(45.0 - 8.0 * min(answer_mentions, 5), 0.0)
        else:
            core_gate_penalty = 45.0

    question_fuzzy = fuzzy_ratio(q_compact, question_compact)
    token_score_q = token_overlap_score(q_tokens, question_tokens)
    token_score_all = token_overlap_score(q_tokens, question_tokens + answer_tokens)

    exact_bonus = 0.0
    reasons = []

    if q_compact and question_compact:
        if q_compact in question_compact or question_compact in q_compact:
            exact_bonus += 22.0
            reasons.append("exact")

    if q_core_terms and (q_core_terms & row_core_terms):
        exact_bonus += 28.0
        reasons.append("core_term")

    # “讲讲mysql”这种极短查询，核心技术词命中应该很重要
    if len(q_tokens) <= 3 and q_core_terms and (q_core_terms & row_core_terms):
        exact_bonus += 10.0
        reasons.append("short_core")

    # 问题标题权重最高，答案只作为辅助
    score = (
        question_fuzzy * 0.42
        + token_score_q * 0.34
        + token_score_all * 0.14
        + exact_bonus
        - core_gate_penalty
    )

    return SearchHit(
        question=question,
        answer=answer,
        score=max(score, 0.0),
        reason=",".join(reasons)
    )


def load_knowledge_rows(db_name=None) -> list[tuple[str, str]]:
    if db_name is None:
        db_name = KNOWLEDGE_DB_PATH

    db_path = Path(db_name)

    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT question, answer
        FROM knowledge
        WHERE question IS NOT NULL
          AND answer IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    return [(str(q), str(a)) for q, a in rows]


def search_knowledge(query: str, db_name=None, top_n: int = 3, min_score: float = 35.0):
    query = (query or "").strip()

    if not query:
        return []

    rows = load_knowledge_rows(db_name)
    if not rows:
        return []

    hits: list[SearchHit] = []

    for question, answer in rows:
        hit = score_row(query, question, answer)
        if hit.score >= min_score:
            hits.append(hit)

    hits.sort(key=lambda h: h.score, reverse=True)

    # 去重：同一个问题只保留最高分
    result = []
    seen_questions = set()

    for hit in hits:
        clean_question = hit.question.strip()
        if clean_question in seen_questions:
            continue

        seen_questions.add(clean_question)
        result.append((hit.question, hit.answer))

        if len(result) >= top_n:
            break

    return result


def debug_search(query: str, db_name=None, top_n: int = 10):
    """命令行调试用：返回带分数的结果"""
    rows = load_knowledge_rows(db_name)
    hits = [score_row(query, q, a) for q, a in rows]
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_n]
