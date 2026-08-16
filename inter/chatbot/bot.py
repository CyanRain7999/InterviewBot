import json
import sqlite3
from pathlib import Path

import fitz  # PyMuPDF
import jieba
import pytesseract
from openai import OpenAI
from PIL import ImageGrab

from app_paths import (
    CONFIG_PATH,
    PROMPT_PATH,
    PROMPT_WENTI_PATH,
    PROMPT_JIANLI_PATH,
    RESUME_INFO_PATH,
    SCREENSHOT_PATH,
    KNOWLEDGE_DB_PATH,
)


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


config = load_config()

tesseract_path = config.get("tesseract_path")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path


client = OpenAI(
    api_key=config.get("OPENAI_API_KEY") or "sk-empty",
    base_url=config.get("API_URL") or "https://api.deepseek.com",
)


def read_text_file(path: Path, default_text: str = "") -> str:
    if not path.exists():
        return default_text

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def ask_llm(user_input: str, system_prompt: str = "") -> str:
    """调用 DeepSeek 官方 OpenAI-compatible API"""
    messages = []

    if system_prompt.strip():
        messages.append({
            "role": "system",
            "content": system_prompt.strip()
        })

    messages.append({
        "role": "user",
        "content": user_input.strip()
    })

    try:
        response = client.chat.completions.create(
            model=config["MODEL_NAME"],
            messages=messages,
            temperature=0.3,
            timeout=30,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"大模型请求失败：{e}"
    

def ask_llm_stream(user_input: str, system_prompt: str = ""):
    """调用 DeepSeek OpenAI-compatible API，流式返回文本片段"""
    messages = []

    base_system_prompt = (
        "你是一个计算机技术面试自检助手。"
        "用户的问题可能来自语音识别，可能存在技术词错误。"
        "如果出现 JMV、jmv、J M V，一律理解为 JVM。"
        "如果出现 JVM 垃圾处理、JVM 垃圾清理、JVM 垃圾管理，一律理解为 JVM 的垃圾回收 GC。"
        "不要把 JVM 垃圾处理理解成现实生活中的垃圾分类、焚烧、填埋或机器人垃圾处理项目。"
        "回答时优先解释计算机、Java、后端、数据库、操作系统、网络、AI Agent 工程化等面试知识。"
    )

    messages.append({
        "role": "system",
        "content": base_system_prompt
    })

    if system_prompt.strip():
        messages.append({
            "role": "system",
            "content": system_prompt.strip()
        })

    messages.append({
        "role": "user",
        "content": user_input.strip()
    })

    response = client.chat.completions.create(
        model=config["MODEL_NAME"],
        messages=messages,
        temperature=0.25,
        max_tokens=380,
        timeout=30,
        stream=True,
    )

    for chunk in response:
        try:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            if content:
                yield content
        except Exception:
            continue


def get_base_interview_prompt() -> str:
    """读取主面试 prompt，并追加已加载的简历信息（如存在）"""
    base = read_text_file(
        PROMPT_PATH,
        default_text=(
            "你是一个后端开发实习面试自检辅助助手。"
            "请根据用户的问题，给出适合中文面试口播的回答。"
        )
    )

    resume = read_text_file(RESUME_INFO_PATH)
    if resume.strip():
        base += "\n\n【我的简历信息】\n" + resume.strip()

    return base


def get_bot_answer_fast(user_message: str) -> str:
    """极速版回答：先给用户一个能立刻念的短答案"""
    system_prompt = get_base_interview_prompt() + """

【本次回答模式：极速版】
你现在只需要给出一段非常适合直接念出来的短回答。

要求：
1. 控制在 80 到 150 个中文字符左右。
2. 不要使用 Markdown。
3. 不要列 1、2、3、4 这种长分点。
4. 用自然口语回答，像面试时直接说出来。
5. 只讲最核心的定义、作用、工程意义。
6. 如果问题很短，要自动理解成“请简要讲讲这个技术点”。
7. 如果存在语音识别错误，要先按后端面试语境纠正再回答。
8. 不要说“极速版”“简短版”这些标签，直接给答案。
9. 先判断题域：后端八股、AI Agent、项目经历、系统设计要分开回答，不要强行套项目。
10. 如果问题表述不标准，先用一句话纠正成更准确的技术表述。
11. 技术术语必须准确，不要写错 TLAB、CAS、JVM、GC、AQS、MVCC 等缩写。
12. 不确定时不要绝对化回答。
"""
    return ask_llm(user_message, system_prompt)


def stream_bot_answer_fast(user_message: str):
    """极速版回答：流式输出"""
    system_prompt = get_base_interview_prompt() + """

【本次回答模式：极速版】
你现在只需要给出一段非常适合直接念出来的短回答。

要求：
1. 控制在 80 到 150 个中文字符左右。
2. 不要使用 Markdown。
3. 不要列 1、2、3、4 这种长分点。
4. 用自然口语回答，像面试时直接说出来。
5. 只讲最核心的定义、作用、工程意义。
6. 如果问题很短，要自动理解成“请简要讲讲这个技术点”。
7. 如果存在语音识别错误，要先按后端面试语境纠正再回答。
8. 不要说“极速版”“简短版”这些标签，直接给答案。
9. 先判断题域：后端八股、AI Agent、项目经历、系统设计要分开回答，不要强行套项目。
10. 如果问题表述不标准，先用一句话纠正成更准确的技术表述。
11. 技术术语必须准确，不要写错 TLAB、CAS、JVM、GC、AQS、MVCC 等缩写。
12. 不确定时不要绝对化回答。
"""
    yield from ask_llm_stream(user_message, system_prompt)


def get_bot_answer_detail(user_message: str) -> str:
    """详细版回答：在极速版之后补充展开"""
    system_prompt = get_base_interview_prompt() + """

【本次回答模式：详细补充版】
你现在需要在极速回答之后，给出一个更完整但仍然适合面试口播的补充回答。

要求：
1. 控制在 280 到 520 个中文字符左右。
2. 回答必须适合直接念出来，不要像教材摘抄，也不要像 Markdown 笔记。
3. 回答前先判断题域：Java 后端八股、AI Agent 工程化、项目经历、系统设计、职业表达要分开处理，不要全部强行套到后端项目。
4. 如果用户问题表述不严谨，先纠正成更准确的技术说法，再回答。
5. 技术术语必须准确，例如 TLAB、CAS、JVM、GC、JMM、AQS、MVCC、B+Tree，不允许拼错。
6. 如果提到“几个性质”“几种情况”“几个步骤”“几个阶段”“几个核心点”，必须把这些内容完整列出来；如果不能完整列出，就不要说具体数字。
7. 不要使用“比如”“等等”“之类的”来省略关键内容。
8. 技术题要优先覆盖：定义、核心机制、常见追问点、工程意义。
9. AI Agent / Skills / Prompt 类问题，要从工程化复用、工具调用、上下文管理、工作流编排、稳定性和可维护性回答。
10. 不要强行把所有问题都关联到我的实习项目。只有自然相关时，才补一句工程实践理解。
11. 不要说“下面是详细版”“补充如下”这种提示语，直接回答正文。
"""
    return ask_llm(user_message, system_prompt)


def get_bot_answer(user_message: str) -> str:
    """保留旧接口，默认走详细回答，避免其他地方报错"""
    return get_bot_answer_detail(user_message)


def get_bot_answer_wenti(user_message: str) -> str:
    """截图题目问答"""
    system_prompt = read_text_file(
        PROMPT_WENTI_PATH,
        default_text=(
            "你是一个面试题解析助手。"
            "请识别用户给出的题目文本，并给出简洁准确的答案。"
        )
    )
    return ask_llm(user_message, system_prompt)


def get_bot_answer_jianli(user_message: str) -> str:
    """简历信息整理"""
    system_prompt = read_text_file(
        PROMPT_JIANLI_PATH,
        default_text=(
            "你是一个简历信息整理助手。"
            "请从用户提供的简历文本中提取面试相关信息，并整理成可用于面试自检的提示词。"
        )
    )
    return ask_llm(user_message, system_prompt)


def capture_and_extract_text() -> str:
    """截图并 OCR 提取文字"""
    try:
        screenshot = ImageGrab.grab()
        SCREENSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        screenshot.save(SCREENSHOT_PATH)

        text = pytesseract.image_to_string(screenshot, lang="chi_sim+eng")
        text = text.strip()

        if not text:
            return "截图 OCR 未识别到有效文字。"

        return text

    except Exception as e:
        return f"截图 OCR 失败：{e}"


def extract_pdf_text(pdf_path: str) -> str:
    """从 PDF 中提取文本"""
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return f"PDF 文件不存在：{pdf_path}"

    texts = []

    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            page_text = page.get_text()
            if page_text:
                texts.append(page_text)
        doc.close()
    except Exception as e:
        return f"PDF 读取失败：{e}"

    return "\n".join(texts).strip()


def generate_prompt(file_path: str) -> str:
    """读取简历 PDF，生成个人背景信息写入 resume_info.txt（不影响主 prompt，加载后立即生效）"""
    resume_text = extract_pdf_text(file_path)

    if not resume_text or resume_text.startswith("PDF "):
        return resume_text or "简历文本提取失败。"

    extracted_info = get_bot_answer_jianli(resume_text)

    RESUME_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(RESUME_INFO_PATH, "w", encoding="utf-8") as f:
        f.write(extracted_info)

    return extracted_info


def get_kg_answer(query: str, db_name=None, top_n: int = 3):
    """使用新检索器查询本地知识库"""
    try:
        from chatbot.retriever import search_knowledge
        return search_knowledge(query, db_name=db_name, top_n=top_n, min_score=35.0)
    except Exception as e:
        print(f"知识库检索失败：{e}")
        return []