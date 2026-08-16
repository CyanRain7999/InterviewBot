# 面试助手 InterviewBot 🚀

基于 **PyQt5** 的桌面面试自检辅助工具：模拟面试场景，实时听题、识题、答题，帮助训练面试口播与临场反应。

> ⚠️ **仅用于面试模拟与自我训练，禁止用于面试作弊**，任何使用后果由使用者自负。

## 功能一览

| 功能 | 说明 |
|---|---|
| 💬 聊天问答 | 输入问题回车发送，大模型**流式输出「口播短答」**（80~150 字，可直接念出来）；勾选「详细版」再后台生成 280~520 字展开回答 |
| 🎤 录音提问 | 手动录音：点一下开始、再点停止并识别。录音中**边识别边匹配**（实时显示识别文字与本地题库候选），停止后做完整识别兜底 |
| 🤖 自动录音 | WebRTC VAD 语音活动检测：检测到说话自动开始录，静音 2.5 秒自动停止并识别，循环监听；静音阈值可在配置中调整 |
| 🔊 系统声音内录 | 默认录制「系统声音（WASAPI loopback）」，只录会议软件（腾讯会议/飞书等）播放的面试官声音，**不会录到你自己**；线下面试可切回麦克风 |
| 📷 截图解题 | 截取当前屏幕并 OCR 识别编程题，自动给出解法分析 + Python 代码（快捷键 `Ctrl+Alt`，需安装 Tesseract OCR） |
| 📄 简历加载 | 加载简历 PDF，提取个人信息后自动拼入系统提示词，之后的回答带上你的个人背景（即时生效，无需重启） |
| 📕 本地知识库 | 导入 Excel 问答库（「问题」「答案」两列）到 SQLite；勾选「知识库」后优先检索本地答案，未命中再走大模型 |
| 🎨 透明主题 | 无边框透明窗口，四种文字主题（白字 / 黑字 / 红字 / 大字）适配不同屏幕与观看距离；「☰」或按住空白处拖动窗口 |

## 环境要求

- Windows 10/11（录音内录、CUDA 加速为 Windows 特性）
- Python 3.9+（开发环境为 3.11）
- 可选：NVIDIA 独立显卡（语音识别 CUDA 加速）

## 从零安装

```bat
:: 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

:: 2. 生成配置文件并填入你的 API Key
copy inter\config\config.example.json inter\config\config.json
::    编辑 inter\config\config.json，至少填写 OPENAI_API_KEY

:: 3. 启动
start.bat
```

> 首次启动 `start.bat` 会自动拉起本地语音识别服务（whisper），需等待模型加载，日志提示「ASR server is ready」后即可正常使用语音功能。

## 获取语音识别模型（二选一）

- **方式 A（推荐，识别效果最好）**：下载 faster-whisper-large-v3-turbo 放到 `models/faster-whisper-large-v3-turbo/`（约 1.5GB，可自行从 Hugging Face 下载，如 `Systran/faster-whisper-large-v3-turbo`）
- **方式 B（零配置）**：把 `config.json` 中 `WHISPER_MODEL` 改为 `small`，首次识别时 faster-whisper 会自动从 Hugging Face 下载小模型

无 NVIDIA 独显时，把 `WHISPER_DEVICE` 改为 `cpu`、`WHISPER_COMPUTE_TYPE` 改为 `int8`。

## 项目结构

```
InterviewBot/
├── start.bat                  # 一键启动：拉起 ASR 服务 + 主界面
├── requirements.txt           # Python 依赖清单
├── inter/                     # 应用主体
│   ├── main.py                # 入口：启动 PyQt5 主窗口
│   ├── app_paths.py           # 统一路径常量
│   ├── asr_server.py          # Whisper 常驻 HTTP 语音识别服务（独立进程）
│   ├── config/
│   │   └── config.example.json    # 配置模板（复制为 config.json 后填写，config.json 已被 .gitignore 排除）
│   ├── prompt/                # 提示词模板
│   │   ├── prompt.txt         #   主面试提示词（个人背景占位，请自行填写）
│   │   ├── prompt_wenti.txt   #   截图题目解题提示词
│   │   └── prompt_jianli.txt  #   简历信息提取提示词
│   ├── knowledge/             # 本地知识库 SQLite（运行时生成）
│   ├── assets/                # 录音、截图等临时文件（运行时生成）
│   └── chatbot/               # 核心逻辑
│       ├── ui.py              #   主界面（透明无边框、录音/自动录音/流式识别）
│       ├── bot.py             #   大模型调用、截图 OCR、简历 PDF、知识库入口
│       ├── retriever.py       #   知识库检索器（jieba+rapidfuzz 打分、技术词门控）
│       ├── text_normalizer.py #   语音识别技术词纠错（JMV→JVM、买色口→MySQL 等）
│       ├── autovad.py         #   WebRTC VAD 自动录音状态机
│       ├── utils.py           #   语音识别统一入口（baidu / whisper 多模式）
│       ├── asr_whisper*.py    #   faster-whisper 封装（热词、prompt 泄漏过滤、多运行模式）
│       ├── taskthread.py      #   后台任务线程
│       └── streamthread.py    #   流式输出线程
└── tools/                     # 题库构建流水线脚本
    ├── extract_javabetter_questions.py     # 抓取 javabetter 面试问题
    ├── prepare_javabetter_kg.py            # 清洗生成待补答案的题库表
    ├── generate_javabetter_answers.py      # 调用 DeepSeek 批量生成答案
    ├── export_javabetter_kg_import.py      # 导出 UI 可导入的问答 Excel
    ├── export_javabetter_question_refs_import.py  # 导出「召回型」问题清单
    └── debug_retriever.py                  # 检索效果调试
```

> 仓库不包含：`models/`（大模型文件）、`data/`（题库原始数据，可经 tools/ 重新生成）、`.venv/`、运行时产物——均已被 `.gitignore` 排除。

## 语音识别架构

`inter/chatbot/utils.py` 是语音识别统一入口，`ASR_PROVIDER` 决定走哪家：

- **`whisper`（默认，本地免费离线）**
  - 默认**常驻服务模式**（`WHISPER_RUN_MODE=server`）：由 `asr_server.py` 在独立进程加载 faster-whisper，提供 `GET /health`、`POST /asr` 两个接口
  - 模型**只加载一次**，避免 PyQt 进程内直接加载 ctranslate2 的原生崩溃与反复加载延迟
  - Windows 下自动把 pip 安装的 NVIDIA CUDA 运行库（cuBLAS/cuDNN）加入 DLL 搜索路径，**无需安装 CUDA Toolkit**
  - 识别时注入技术词热词（hotwords）与 initial prompt（MySQL/Redis/JVM/GC/…），并过滤 Whisper 偶发的「prompt 泄漏」
  - 另有两种备用模式：`subprocess`（每次识别起子进程，稳定但慢）、`inprocess`（调试用，不推荐）
- **`baidu`（百度云）**：需配置 `API_KEY` / `SECRET_KEY`（短语音识别）

### 流式识别

录音过程中每 1.5 秒把最近 20 秒音频送识别一次，实时显示识别文本并同步匹配本地题库候选；停止录音后再做一次完整识别兜底。自动模式下，若完整识别与流式文本一致则直接采用流式结果（零等待出答案），更长音频则自动补全更新。

## 配置参考（inter/config/config.json）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `API_URL` | `https://api.deepseek.com` | 大模型 API 地址（OpenAI 兼容） |
| `MODEL_NAME` | `deepseek-v4-flash` | 大模型名称 |
| `OPENAI_API_KEY` | — | 大模型 Key（必填） |
| `ASR_PROVIDER` | `whisper` | 语音识别：`whisper`（本地）或 `baidu`（云端） |
| `API_KEY` / `SECRET_KEY` | — | 百度云 ASR 密钥（`ASR_PROVIDER=baidu` 时使用） |
| `BAIDU_ASR_DEV_PID` | `1537` | 百度 ASR 识别模型（普通话） |
| `WHISPER_RUN_MODE` | `server` | `server` / `subprocess` / `inprocess` |
| `WHISPER_SERVER_HOST/PORT/URL` | `127.0.0.1:8765` | 常驻服务地址 |
| `WHISPER_MODEL` | `models/faster-whisper-large-v3-turbo` | 模型路径或名称；想用轻量模型改为 `small`（自动下载） |
| `WHISPER_DEVICE` | `cuda` | 无 NVIDIA 独显时改为 `cpu` |
| `WHISPER_COMPUTE_TYPE` | `int8_float16` | 无独显时改为 `int8` |
| `WHISPER_TIMEOUT` | `120` | 单次识别超时（秒） |
| `tesseract_path` | `D:\ocr\tesseract.exe` | Tesseract OCR 路径（截图解题用，需自装 chi_sim+eng 语言包） |
| `AUTO_VAD_SILENCE_SECONDS` | `2.5` | 自动录音静音判定时长：对方思考停顿多可调大到 3~4，追求快速出答案可调小到 1.5 |

## 构建知识库

### 方式一：界面直接导入

1. 用 Excel 准备问答数据，两列：`问题`、`答案`
2. 点击顶部「📕 题库」选择该 Excel 文件（自动去重写入 `inter/knowledge/knowledge.db`）
3. 勾选「知识库」即可优先检索本地答案

### 方式二：tools 流水线（javabetter 题库）

基于 javabetter.cn「面渣逆袭」构建（`data/` 不随仓库分发，需运行脚本生成）：

```bash
# 1. 抓取 javabetter 面试问题标题 → data/javabetter_questions.xlsx / .csv
python tools/extract_javabetter_questions.py

# 2. 清洗并生成待补全答案的题库表 → data/javabetter_kg_workbook.xlsx
python tools/prepare_javabetter_kg.py

# 3. 调用 DeepSeek 批量生成答案（可选按分类、限量）
python tools/generate_javabetter_answers.py --category JVM --limit 10
python tools/generate_javabetter_answers.py --limit 100

# 4. 导出为 UI 可直接导入的问答 Excel → data/javabetter_kg_import.xlsx
python tools/export_javabetter_kg_import.py

# （可选）不生成答案，仅导出「召回型」问题清单
python tools/export_javabetter_question_refs_import.py

# 调试检索效果
python tools/debug_retriever.py "讲讲mysql"
```

### 检索器特性

- 中文 + 英文技术词混合分词（jieba），可选 rapidfuzz 模糊匹配
- **语音识别纠错同义词归一**：JMV→JVM、买色口/麦色口→MySQL、瑞迪斯→Redis、斯普林布特→Spring Boot、垃圾处理→垃圾回收 等
- **核心技术词门控**：查询含 MySQL/Redis/JVM 等强主题词时，候选题不含该词会被强烈降权，避免「讲讲 MySQL」召回 JVM 题
- 全表扫描打分，对 1000~5000 条题库足够快；返回 `[(问题, 答案), ...]` 格式

## 常见问题

- **黑窗口一闪而过**：右键 `start.bat` →「编辑」查看内容，或把窗口截图发出来排查
- **语音不可用 / 识别一直失败**：确认已复制 `config.example.json` 为 `config.json` 且 `ASR_PROVIDER=whisper`；无独显需 `WHISPER_DEVICE=cpu` + `WHISPER_COMPUTE_TYPE=int8`；whisper 首次加载较慢，请等待「ASR server is ready」
- **没装 Tesseract**：截图解题会报错；安装 Tesseract 并在 `tesseract_path` 配置路径，语言包需含 `chi_sim` 与 `eng`
- **录音源怎么选**：下拉框默认「系统声音（内录）」（WASAPI loopback），只录面试官声音不录自己；线下面试切回「麦克风」

## 免责声明

此工具仅用于面试模拟与自我训练，**不推荐也禁止用于面试作弊**。任何使用后果与项目及作者无关。

## License

[MIT](LICENSE)
