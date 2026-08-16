from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config" / "config.json"

PROMPT_DIR = BASE_DIR / "prompt"
PROMPT_PATH = PROMPT_DIR / "prompt.txt"
PROMPT_WENTI_PATH = PROMPT_DIR / "prompt_wenti.txt"
PROMPT_JIANLI_PATH = PROMPT_DIR / "prompt_jianli.txt"
RESUME_INFO_PATH = PROMPT_DIR / "resume_info.txt"

ASSETS_DIR = BASE_DIR / "assets"
RECORDED_AUDIO_PATH = ASSETS_DIR / "recorded_audio.wav"
SCREENSHOT_PATH = ASSETS_DIR / "screenshot.png"

KNOWLEDGE_DIR = BASE_DIR / "knowledge"
KNOWLEDGE_DB_PATH = KNOWLEDGE_DIR / "knowledge.db"

PROJECT_ROOT = BASE_DIR.parent
MODELS_DIR = PROJECT_ROOT / "models"