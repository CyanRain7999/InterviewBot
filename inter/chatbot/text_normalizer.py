# -*- coding: utf-8 -*-
import re


def normalize_interview_text(text: str) -> str:
    """修正语音识别和手动输入中的常见技术词错误"""
    if not text:
        return ""

    s = text.strip()
    s = re.sub(r"\s+", " ", s)

    # JVM 常见误识别
    s = re.sub(r"\bJMV\b", "JVM", s, flags=re.IGNORECASE)
    s = re.sub(r"\bjmv\b", "JVM", s, flags=re.IGNORECASE)
    s = re.sub(r"\bjvm\b", "JVM", s, flags=re.IGNORECASE)
    s = s.replace("J M V", "JVM")
    s = s.replace("J M W", "JVM")
    s = s.replace("java虚拟机", "JVM")
    s = s.replace("Java虚拟机", "JVM")
    s = s.replace("JAVA虚拟机", "JVM")

    # GC / 垃圾回收
    s = re.sub(r"\bgc\b", "GC", s, flags=re.IGNORECASE)
    s = s.replace("垃圾处理", "垃圾回收")
    s = s.replace("垃圾清理", "垃圾回收")
    s = s.replace("垃圾管理", "垃圾回收")
    s = s.replace("所引", "索引")
    s = s.replace("锁引", "索引")

    # MySQL 常见误识别
    mysql_words = [
        "买色口", "麦色口", "麦涩口", "买涩口",
        "买SQL", "麦SQL", "my sql", "mysql"
    ]
    for w in mysql_words:
        s = re.sub(re.escape(w), "MySQL", s, flags=re.IGNORECASE)

    # Redis 常见误识别
    redis_words = ["瑞迪斯", "雷迪斯", "redis"]
    for w in redis_words:
        s = re.sub(re.escape(w), "Redis", s, flags=re.IGNORECASE)

    # HashMap / Hashtable 常见误识别（中英文音译）
    hashmap_words = ["哈西麦普", "哈希麦普", "哈西玛普", "哈希玛普", "哈希表"]
    for w in hashmap_words:
        s = re.sub(re.escape(w), "HashMap", s)
    s = re.sub(re.escape("哈西特保"), "Hashtable", s)

    # Spring / Spring Boot
    s = re.sub(r"\bspringboot\b", "Spring Boot", s, flags=re.IGNORECASE)
    s = re.sub(r"\bspring boot\b", "Spring Boot", s, flags=re.IGNORECASE)
    s = s.replace("斯普林布特", "Spring Boot")
    s = s.replace("斯普林 boot", "Spring Boot")
    s = s.replace("斯普林", "Spring")

    # 常见后端缩写
    s = re.sub(r"\btlab\b", "TLAB", s, flags=re.IGNORECASE)
    s = re.sub(r"\bcas\b", "CAS", s, flags=re.IGNORECASE)
    s = re.sub(r"\baqs\b", "AQS", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmvc\b", "MVC", s, flags=re.IGNORECASE)
    s = re.sub(r"\bmvcc\b", "MVCC", s, flags=re.IGNORECASE)
    s = re.sub(r"\bbtree\b", "B-Tree", s, flags=re.IGNORECASE)

    # 网络 / 协议
    s = re.sub(r"\bhttp\b", "HTTP", s, flags=re.IGNORECASE)
    s = re.sub(r"\bhttps\b", "HTTPS", s, flags=re.IGNORECASE)
    s = re.sub(r"\btcp\b", "TCP", s, flags=re.IGNORECASE)
    s = re.sub(r"\budp\b", "UDP", s, flags=re.IGNORECASE)

    # JVM + 垃圾回收组合规范化
    if re.search(r"JVM", s, flags=re.IGNORECASE) and "垃圾回收" in s:
        s = "JVM 的垃圾回收"

    return s