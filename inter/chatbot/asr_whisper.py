from pathlib import Path

from faster_whisper import WhisperModel

from app_paths import PROJECT_ROOT

_model_cache = {}

# 注意：这里不要写太长，否则低置信/空音频时 Whisper 偶尔会把 prompt 本身吐出来。
TECH_INITIAL_PROMPT = (
    "中文后端开发面试。保留英文技术词：MySQL, Redis, Spring Boot, JVM, GC, TLAB, CAS, AQS, MVCC, InnoDB, SQL, Java。"
)

TECH_HOTWORDS = (
    "MySQL Redis Spring Boot Spring JVM GC TLAB CAS AQS JMM MVCC InnoDB B+Tree "
    "HashMap ConcurrentHashMap ThreadLocal MyBatis RocketMQ HTTP HTTPS TCP UDP SQL Java Golang "
    "索引 事务 隔离级别 锁 表锁 行锁 间隙锁 临键锁 回表 覆盖索引 最左前缀 慢查询 "
    "垃圾回收 类加载 双亲委派 对象分配 堆 栈 方法区 元空间 Eden Survivor 老年代 年轻代"
)

PROMPT_LEAK_PATTERNS = [
    "请尽量保留英文技术词",
    "请尽量保留英文技术原文",
    "不要把英文技术词音译成中文",
    "不要把英文技术音译成中文",
    "中文后端开发面试",
    "常见技术词包括",
]


def resolve_model_path(model_name_or_path: str) -> str:
    """
    支持三种写法：
    1. small / base / medium 这种模型名，走 Hugging Face 自动下载
    2. models/faster-whisper-small 这种项目根目录相对路径
    3. C:/xxx/models/faster-whisper-small 这种绝对路径
    """
    raw = str(model_name_or_path or "").strip()

    if not raw:
        raw = "small"

    possible_path = Path(raw)

    if possible_path.is_absolute():
        return str(possible_path)

    project_relative = PROJECT_ROOT / possible_path
    if project_relative.exists():
        return str(project_relative)

    cwd_relative = Path.cwd() / possible_path
    if cwd_relative.exists():
        return str(cwd_relative.resolve())

    # 不存在就当作模型名交给 faster-whisper，例如 small/base/medium
    return raw


def is_prompt_leak(text: str) -> bool:
    """过滤 Whisper 把 initial_prompt 当成识别结果吐出的情况"""
    normalized = (text or "").strip()

    if not normalized:
        return False

    if normalized == TECH_INITIAL_PROMPT:
        return True

    for pattern in PROMPT_LEAK_PATTERNS:
        if pattern in normalized:
            return True

    # 过短且只像提示词残片，也过滤
    if "英文技术" in normalized and ("保留" in normalized or "音译" in normalized):
        return True

    return False


def get_whisper_model(model_name: str, device: str, compute_type: str):
    model_path = resolve_model_path(model_name)
    key = (model_path, device, compute_type)

    if key not in _model_cache:
        print(f"[Whisper] loading model: {model_path}")
        print(f"[Whisper] device={device}, compute_type={compute_type}")
        print(f"[Whisper] local_files_only={Path(model_path).exists()}")

        _model_cache[key] = WhisperModel(
            model_path,
            device=device,
            compute_type=compute_type,
            local_files_only=Path(model_path).exists()
        )

        print("[Whisper] model loaded")

    return _model_cache[key]


def transcribe_with_options(model, wav_file_path: Path, use_hotwords: bool = True):
    kwargs = {
        "language": None,
        "task": "transcribe",
        "beam_size": 5,
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 300
        },
        "initial_prompt": TECH_INITIAL_PROMPT,
        "condition_on_previous_text": False,
        # 提高一点阈值，减少空音频/低置信时胡乱吐 prompt 的概率
        "no_speech_threshold": 0.6,
        "log_prob_threshold": -1.0,
        "compression_ratio_threshold": 2.4,
    }

    if use_hotwords:
        kwargs["hotwords"] = TECH_HOTWORDS

    segments, info = model.transcribe(str(wav_file_path), **kwargs)

    text_parts = []

    for segment in segments:
        text = segment.text.strip()
        if text and not is_prompt_leak(text):
            text_parts.append(text)

    return " ".join(text_parts).strip()


def whisper_speech_to_text(
    wav_file_path,
    model_name="small",
    device="cpu",
    compute_type="int8"
):
    wav_file_path = Path(wav_file_path)

    if not wav_file_path.exists():
        return {
            "err_no": -1,
            "err_msg": f"音频文件不存在：{wav_file_path}",
            "result": []
        }

    try:
        model = get_whisper_model(model_name, device, compute_type)

        try:
            text = transcribe_with_options(model, wav_file_path, use_hotwords=True)
        except TypeError as e:
            # 兼容少数 faster-whisper 版本不支持 hotwords 参数的情况
            if "hotwords" not in str(e):
                raise
            text = transcribe_with_options(model, wav_file_path, use_hotwords=False)

        if is_prompt_leak(text):
            return {
                "err_no": -4,
                "err_msg": "Whisper 输出疑似 prompt 泄漏，已过滤。请重新录音。",
                "result": []
            }

        if not text:
            return {
                "err_no": -2,
                "err_msg": "Whisper 未识别到有效文本",
                "result": []
            }

        return {
            "err_no": 0,
            "err_msg": "success.",
            "result": [text]
        }

    except Exception as e:
        return {
            "err_no": -3,
            "err_msg": f"Whisper 识别失败：{repr(e)}",
            "result": []
        }
