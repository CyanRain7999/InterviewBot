# -*- coding: utf-8 -*-
"""
面试助手主界面（透明无边框版）。
改造目标：界面清晰、操作直观、全中文。
"""
import re
import sqlite3

import pandas as pd
import wave

from PyQt5.QtCore import Qt, QTimer, QSettings
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QLabel, QRadioButton,
    QCheckBox, QComboBox,
)

from chatbot.bot import (
    get_bot_answer_detail,
    stream_bot_answer_fast,
    get_bot_answer_wenti,
    capture_and_extract_text,
    generate_prompt,
    get_kg_answer,
    load_config,
)
from chatbot.utils import speech_to_text, whisper_speech_to_text_server, get_config
from chatbot.autovad import AutoVad
from chatbot.text_normalizer import normalize_interview_text
from chatbot.taskthread import TaskThread
from chatbot.streamthread import StreamTaskThread
from app_paths import ASSETS_DIR, RECORDED_AUDIO_PATH, KNOWLEDGE_DB_PATH

# ---------------------------------------------------------------- 外观主题
# 透明窗口上的聊天文字样式：名字 → (背景, 文字颜色, 字号)
THEMES = {
    "白字": {"bg": "rgba(0, 0, 0, 70)",    "fg": "white",   "size": 18, "padding": "8px"},
    "黑字": {"bg": "rgba(255,255,255,140)", "fg": "black",   "size": 18, "padding": "8px"},
    "红字": {"bg": "rgba(0, 0, 0, 70)",    "fg": "red",     "size": 22, "padding": "8px"},
    "大字": {"bg": "rgba(0, 0, 0, 215)",   "fg": "#FFD60A", "size": 32, "padding": "14px"},
}
DEFAULT_THEME = "白字"

BUTTON_STYLE = """
    background-color: rgba(0, 0, 0, 150);
    color: white;
    font-size: 14px;
    padding: 5px;
    border-radius: 8px;
"""
CHECKBOX_STYLE = """
    background-color: rgba(0, 0, 0, 150);
    color: white;
    font-size: 13px;
    padding: 4px 8px;
    border-radius: 8px;
"""


def make_button(text, width=80):
    """统一样式的按钮"""
    btn = QPushButton(text)
    btn.setStyleSheet(BUTTON_STYLE)
    btn.setFixedWidth(width)
    return btn


COMBO_STYLE = """
QComboBox { background-color: rgba(0,0,0,150); color: white; font-size: 13px;
            padding: 3px 6px; border-radius: 8px; }
QComboBox QAbstractItemView { background-color: rgba(40,40,40,240); color: white;
            selection-background-color: rgba(90,90,90,255); }
"""

# 流式识别间隔（毫秒）：每 1.5 秒把已录音频送识别一次
STREAM_INTERVAL_MS = 1500
# 流式识别只看最近 20 秒音频，控制每次转写耗时
STREAM_WINDOW_SECONDS = 20


class ChatBotApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("InterviewBot", "InterviewBot")

        self.setWindowTitle("面试助手")
        self.setGeometry(100, 100, 1000, 900)
        self.setWindowFlag(Qt.FramelessWindowHint)      # 无边框
        self.setAttribute(Qt.WA_TranslucentBackground)  # 透明
        self.setStyleSheet("background: transparent;")

        self.is_dragging = False
        self.drag_position = None
        self.active_threads = []

        # 录音源（麦克风 / 系统声音内录）
        self._pa = None
        self.recording_sources = self._enumerate_sources()

        # 流式识别状态
        self.stream_timer = QTimer(self)
        self.stream_timer.setInterval(STREAM_INTERVAL_MS)
        self.stream_timer.timeout.connect(self._stream_recognize)
        self.stream_gen = 0
        self.stream_busy = False
        self.stream_last_text = ""
        self._auto_pending_full = False
        self.record_rate = 16000
        self.record_channels = 1

        # 自动录音（VAD）状态
        self.auto_mode = False
        self.auto_busy = False
        try:
            silence_secs = float(load_config().get("AUTO_VAD_SILENCE_SECONDS", 2.5))
        except Exception:
            silence_secs = 2.5
        self.auto_vad = AutoVad(mode=1, silence_stop_frames=max(50, int(silence_secs * 50)))
        self.auto_stream = None
        self.auto_audio = None
        self.auto_rate = 16000
        self.auto_channels = 1
        self._auto_pcm = b""
        self.auto_cooldown_until = 0.0
        self.auto_timer = QTimer(self)
        self.auto_timer.setInterval(20)
        self.auto_timer.timeout.connect(self._auto_tick)

        self._build_ui()
        self._apply_theme(self.settings.value("theme", DEFAULT_THEME))
        self._check_config()

        self.chat_history.append(
            "面试助手已就绪。\n"
            "· 输入问题后按回车发送\n"
            "· 🎤 录音说话（再点一次停止并识别）\n"
            "· 📷 截图识别编程题（或按 Ctrl+Alt）\n"
            "· ☰ 或按住窗口空白处拖动\n"
        )

    # ------------------------------------------------------------ 界面搭建
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ---- 顶部：标题 + 主题切换 + 窗口控制 ----
        top = QHBoxLayout()
        title = QLabel("面试助手")
        title.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold;"
            "background-color: rgba(0,0,0,120); border-radius: 6px; padding: 4px 10px;"
        )
        top.addWidget(title)
        top.addStretch(1)

        self.theme_radios = {}
        for name in THEMES:
            radio = QRadioButton(name)
            radio.setStyleSheet(CHECKBOX_STYLE)
            radio.setToolTip({"白字": "白字黑底（推荐）", "黑字": "黑字白底",
                              "红字": "原版红色高亮", "大字": "高对比大黄字，远距离可读"}[name])
            radio.toggled.connect(
                lambda checked, n=name: self._apply_theme(n) if checked else None
            )
            self.theme_radios[name] = radio
            top.addWidget(radio)

        self.kg_button = make_button("📕 题库", 70)
        self.kg_button.setToolTip("导入 Excel 问答库（含「问题」「答案」两列）")
        self.kg_button.clicked.connect(self.stru_kg)
        top.addWidget(self.kg_button)

        self.drag_button = make_button("☰", 40)
        self.drag_button.setToolTip("拖动窗口")
        self.drag_button.pressed.connect(self.start_drag)
        top.addWidget(self.drag_button)

        self.close_button = make_button("✕", 40)
        self.close_button.setStyleSheet(
            "background-color: rgba(255, 0, 0, 180); color: white;"
            "font-size: 14px; padding: 5px; border-radius: 8px;"
        )
        self.close_button.setToolTip("关闭")
        self.close_button.clicked.connect(self.close)
        top.addWidget(self.close_button)

        layout.addLayout(top)

        # ---- 聊天记录 ----
        self.chat_history = QTextEdit(self)
        self.chat_history.setReadOnly(True)
        layout.addWidget(self.chat_history, 1)

        # ---- 实时识别区（录音中显示，边识别边匹配） ----
        self.realtime_label = QLabel("")
        self.realtime_label.setStyleSheet(
            "background-color: rgba(0,0,0,190); color: #FFD60A;"
            "font-size: 15px; font-weight: bold; padding: 6px 10px; border-radius: 6px;"
        )
        self.realtime_label.setWordWrap(True)
        self.realtime_label.hide()
        layout.addWidget(self.realtime_label)

        # ---- 输入行 ----
        input_row = QHBoxLayout()
        self.user_input = QLineEdit(self)
        self.user_input.setPlaceholderText("输入面试问题，回车发送…")
        self.user_input.setStyleSheet(
            "background-color: rgba(0, 0, 0, 200); color: white;"
            "font-size: 14px; padding: 8px; border-radius: 8px;"
        )
        self.user_input.returnPressed.connect(self.send_message)
        self.user_input.installEventFilter(self)  # 保留 Ctrl+Alt 截图快捷键
        input_row.addWidget(self.user_input, 1)

        self.send_button = make_button("发送", 70)
        self.send_button.clicked.connect(self.send_message)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        # ---- 底部工具栏 ----
        bar = QHBoxLayout()

        self.source_combo = QComboBox(self)
        for src in self.recording_sources:
            self.source_combo.addItem(src["name"])
        # 默认选第一个系统声音（内录）设备：只录会议软件输出，不会录到自己
        loop_idx = next(
            (i for i, s in enumerate(self.recording_sources)
             if s["loopback_index"] is not None),
            None,
        )
        if loop_idx is not None:
            self.source_combo.setCurrentIndex(loop_idx)
        self.source_combo.setStyleSheet(COMBO_STYLE)
        self.source_combo.setToolTip(
            "录音源：系统声音（内录腾讯会议/飞书，不会录到自己的麦克风），或麦克风（线下场景）"
        )
        bar.addWidget(self.source_combo)

        self.voice_button = make_button("🎤 录音", 90)
        self.voice_button.clicked.connect(self.toggle_recording)
        bar.addWidget(self.voice_button)

        self.auto_button = make_button("🤖 自动", 90)
        self.auto_button.setToolTip("自动录音：检测到说话自动开始，静音 1.5 秒自动停止并识别")
        self.auto_button.clicked.connect(self.toggle_auto)
        bar.addWidget(self.auto_button)

        self.capture_button = make_button("📷 截图", 90)
        self.capture_button.clicked.connect(self.on_capture_button_click)
        bar.addWidget(self.capture_button)

        self.clear_button = make_button("清空", 70)
        self.clear_button.clicked.connect(self.clear_chat_history)
        bar.addWidget(self.clear_button)

        self.resume_button = make_button("📄 简历", 80)
        self.resume_button.clicked.connect(self.load_resume)
        bar.addWidget(self.resume_button)

        self.kg_check = QCheckBox("知识库")
        self.kg_check.setStyleSheet(CHECKBOX_STYLE)
        self.kg_check.setToolTip("开启后优先从本地题库检索答案")
        bar.addWidget(self.kg_check)

        self.detail_check = QCheckBox("详细版")
        self.detail_check.setStyleSheet(CHECKBOX_STYLE)
        self.detail_check.setToolTip("勾选后除口播短答外，再生成一段详细回答")
        bar.addWidget(self.detail_check)

        bar.addStretch(1)
        layout.addLayout(bar)

        # ---- 录音状态 ----
        self.is_recording = False
        self.audio = None
        self.stream = None
        self.frames = []
        self.output_filename = str(RECORDED_AUDIO_PATH)

        # 默认主题（放在 chat_history 创建之后再触发，避免信号回调访问未创建的控件）
        self.theme_radios[DEFAULT_THEME].setChecked(True)

        self.user_input.setFocus()

    # ------------------------------------------------------------ 主题
    def _apply_theme(self, name):
        if not hasattr(self, "chat_history"):
            return  # 控件未创建完成时（信号提前触发）先跳过
        theme = THEMES.get(name, THEMES[DEFAULT_THEME])
        self.chat_history.setStyleSheet(
            f"background-color: {theme['bg']}; color: {theme['fg']};"
            f"font-size: {theme['size']}px; font-weight: bold;"
            f"padding: {theme.get('padding', '8px')};"
        )
        self.settings.setValue("theme", name)

    # ------------------------------------------------------------ 配置检查
    def _check_config(self):
        try:
            cfg = load_config()
        except Exception:
            cfg = {}
        key = (cfg.get("OPENAI_API_KEY") or "").strip()
        if not key or key.lower() in ("key", "sk-xxx", "your-openai-api-key"):
            QMessageBox.warning(
                self, "缺少 API Key",
                "还没有配置大模型 API Key。\n\n"
                "请打开 inter/config/config.json，\n"
                "把 OPENAI_API_KEY 换成你自己的 Key。",
            )

    # ------------------------------------------------------------ 提问回答
    def ask_ai_answer(self, question):
        """流式输出口播短答；勾选「详细版」时再后台生成一段详细回答"""
        self.chat_history.append("")
        self.chat_history.append("【回答】")
        self.chat_history.moveCursor(self.chat_history.textCursor().End)

        stream_thread = StreamTaskThread(stream_bot_answer_fast, question)
        stream_thread.chunk_signal.connect(self.append_stream_chunk)
        stream_thread.error_signal.connect(
            lambda error: self.append_answer_block("【回答】", error)
        )
        stream_thread.finished_signal.connect(self.append_stream_end)
        stream_thread.finished_signal.connect(
            lambda t=stream_thread: self._cleanup_thread(t)
        )
        self.active_threads.append(stream_thread)
        stream_thread.start()

        if self.detail_check.isChecked():
            detail_thread = TaskThread(get_bot_answer_detail, question)
            detail_thread.result_signal.connect(
                lambda result: self.append_answer_block("【详细版】", result)
            )
            detail_thread.finished_signal.connect(
                lambda t=detail_thread: self._cleanup_thread(t)
            )
            self.active_threads.append(detail_thread)
            detail_thread.start()

    def send_message(self):
        """处理发送消息事件"""
        raw = self.user_input.text().strip()
        if not raw:
            return

        text = normalize_interview_text(raw)
        self.user_input.clear()

        self.chat_history.append(f"你：{text}\n")

        # 知识库开启时优先检索本地题库
        if self.kg_check.isChecked():
            results = get_kg_answer(text)
            if results:
                self.show_kg_results_compact(results)
            else:
                self.chat_history.append("（本地题库未命中，改用大模型回答）")

        self.ask_ai_answer(text)

    # ------------------------------------------------------------ 流式显示
    def append_answer_block(self, title, result):
        """直接追加一段回答"""
        if isinstance(result, Exception):
            text = f"{title}\n请求失败：{result}"
        else:
            text = str(result).strip()
            if not text:
                text = "（没有生成有效内容）"
            text = f"{title}\n{text}"

        self.chat_history.append(text)
        self.chat_history.append("")
        self._scroll_to_bottom()

    def append_stream_chunk(self, chunk):
        cursor = self.chat_history.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(chunk)
        self.chat_history.setTextCursor(cursor)
        self._scroll_to_bottom()

    def append_stream_end(self):
        self.chat_history.append("")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        self.chat_history.verticalScrollBar().setValue(
            self.chat_history.verticalScrollBar().maximum()
        )

    def _cleanup_thread(self, thread):
        """线程结束后清理引用"""
        if thread in self.active_threads:
            self.active_threads.remove(thread)
        thread.deleteLater()

    # ------------------------------------------------------------ 知识库
    def extract_short_answer(self, answer, max_len=180):
        """从知识库答案中提取口播短答，避免大段文字刷屏"""
        answer = str(answer or "").strip()
        if "【口播短答】" in answer:
            start = answer.find("【口播短答】") + len("【口播短答】")
            end = answer.find("【详细解释】")
            short = answer[start:end].strip() if end > start else answer[start:].strip()
        else:
            short = answer

        short = re.sub(r"\s+", " ", short.replace("\r", " ").replace("\n", " "))
        if len(short) > max_len:
            short = short[:max_len] + "..."
        return short

    def show_kg_results_compact(self, results):
        """紧凑展示知识库命中结果"""
        self.chat_history.append(f"📚 找到 {len(results)} 条相关记录：")
        for idx, (question, answer) in enumerate(results, 1):
            self.chat_history.append(
                f"{idx}. {question}\n    {self.extract_short_answer(answer)}\n"
            )
        self._scroll_to_bottom()

    def stru_kg(self):
        """选择 Excel 并导入知识库"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择问答 Excel 文件", "", "Excel 文件 (*.xlsx)"
        )
        if not file_path:
            return
        self.chat_history.append("正在导入题库，请稍候…")
        self.load_excel_to_db(file_path)

    def load_excel_to_db(self, file_path, db_name=str(KNOWLEDGE_DB_PATH)):
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"无法读取 Excel：{e}")
            return

        if "问题" not in df.columns or "答案" not in df.columns:
            QMessageBox.warning(
                self, "格式错误",
                "Excel 需要包含「问题」和「答案」两列。",
            )
            return

        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL
            )
        """)

        added = 0
        for _, row in df.iterrows():
            question, answer = row["问题"], row["答案"]
            cursor.execute(
                "SELECT COUNT(*) FROM knowledge WHERE question = ? AND answer = ?",
                (question, answer),
            )
            if cursor.fetchone()[0] == 0:
                cursor.execute(
                    "INSERT INTO knowledge (question, answer) VALUES (?, ?)",
                    (question, answer),
                )
                added += 1

        conn.commit()
        conn.close()
        self.show_popup_message(
            "成功", f"题库导入完成，新增 {added} 条。\n勾选「知识库」即可优先检索。"
        )

    # ------------------------------------------------------------ 简历
    def load_resume(self):
        """选择简历 PDF，生成个性化回答用的背景信息"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择简历 PDF", "", "PDF 文件 (*.pdf)"
        )
        if not file_path:
            return
        self.chat_history.append("正在读取简历并生成背景信息，请稍候…")

        self.thread_merge = TaskThread(generate_prompt, file_path)
        self.thread_merge.finished_signal.connect(self.load_resume_done)
        self.thread_merge.finished_signal.connect(self.thread_merge.deleteLater)
        self.thread_merge.start()

    def load_resume_done(self):
        self.show_popup_message(
            "成功", "简历信息已生效，之后的回答都会带上你的个人背景。"
        )

    # ------------------------------------------------------------ 截图题目
    def on_capture_button_click(self):
        self.chat_history.append("正在截取屏幕并识别题目…")
        self.chat_history.append("提示：截图将保存为 assets/screenshot.png，可先截好再点此按钮。")
        text = capture_and_extract_text()
        self.chat_history.append(f"识别到题目：\n{text}\n")

        thread = TaskThread(get_bot_answer_wenti, text)
        thread.result_signal.connect(
            lambda result: self.append_answer_block("【题目解答】", result)
        )
        thread.finished_signal.connect(lambda t=thread: self._cleanup_thread(t))
        self.active_threads.append(thread)
        thread.start()

    # ------------------------------------------------------------ 清空
    def clear_chat_history(self):
        self.chat_history.clear()

    # ------------------------------------------------------------ 窗口拖动
    def start_drag(self):
        self.is_dragging = True
        self.drag_position = QCursor.pos() - self.frameGeometry().topLeft()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.is_dragging:
            self.move(event.globalPos() - self.drag_position)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_dragging = False

    def eventFilter(self, source, event):
        """快捷键：Ctrl+Alt 截图"""
        if event.type() == event.KeyPress:
            if event.modifiers() == (Qt.ControlModifier | Qt.AltModifier):
                self.capture_button.click()
                return True
        return super().eventFilter(source, event)

    # ------------------------------------------------------------ 录音源
    def _enumerate_sources(self):
        """枚举录音源：麦克风 + WASAPI 系统声音（内录）"""
        sources = []
        try:
            import pyaudiowpatch as pa  # 支持 loopback 内录
            self._pa = pa
            p = pa.PyAudio()
            try:
                sources.append({
                    "name": "麦克风（默认）",
                    "loopback_index": None,
                    "rate": 16000,
                    "channels": 1,
                })
                for i in range(p.get_device_count()):
                    info = p.get_device_info_by_index(i)
                    if info.get("isLoopbackDevice"):
                        rate = int(info.get("defaultSampleRate") or 48000)
                        ch = min(int(info.get("maxInputChannels") or 2), 2)
                        name = str(info.get("name", "")).split(" [Loopback]")[0]
                        sources.append({
                            "name": f"系统声音：{name}",
                            "loopback_index": i,
                            "rate": rate,
                            "channels": ch,
                        })
            finally:
                p.terminate()
        except Exception:
            # 没有 PyAudioWPatch 时退回普通麦克风
            import pyaudio as pa
            self._pa = pa
            sources.append({
                "name": "麦克风（默认）",
                "loopback_index": None,
                "rate": 16000,
                "channels": 1,
            })
        return sources

    # ------------------------------------------------------------ 自动录音（VAD）
    def toggle_auto(self):
        """开关自动录音模式：说话自动开始，静音 1.5 秒自动停止并识别"""
        if self.auto_mode:
            self._exit_auto()
        else:
            self._enter_auto()

    def _enter_auto(self):
        if self.auto_mode or self.is_recording:
            return
        dev = self.recording_sources[self.source_combo.currentIndex()]
        self.auto_rate = int(dev["rate"])
        self.auto_channels = int(dev["channels"])

        try:
            self.auto_audio = self._pa.PyAudio()
            kwargs = {
                "format": self._pa.paInt16,
                "channels": self.auto_channels,
                "rate": self.auto_rate,
                "input": True,
                "frames_per_buffer": self.auto_rate // 50,  # 20ms 一帧
            }
            if dev["loopback_index"] is not None:
                kwargs["input_device_index"] = dev["loopback_index"]
            self.auto_stream = self.auto_audio.open(**kwargs)
        except Exception as e:
            QMessageBox.warning(self, "自动录音", f"无法打开录音设备：\n{e}")
            return

        self.auto_mode = True
        self.auto_busy = False
        self._auto_pcm = b""
        self.auto_vad.reset()
        self.auto_cooldown_until = 0.0
        self.voice_button.setEnabled(False)
        self.source_combo.setEnabled(False)
        self.auto_button.setText("🤖 自动中")
        self.auto_button.setStyleSheet(
            "background-color: rgba(0, 120, 0, 220); color: white;"
            "font-size: 14px; padding: 5px; border-radius: 8px;"
        )
        self.realtime_label.setText("🤖 自动监听中：说话自动开始，静音 1.5 秒自动识别")
        self.realtime_label.show()
        self.auto_timer.start()

    def _exit_auto(self):
        self.auto_timer.stop()
        if self.is_recording:
            self._auto_stop_recording()
        if self.auto_stream is not None:
            try:
                self.auto_stream.stop_stream()
                self.auto_stream.close()
            except Exception:
                pass
            self.auto_stream = None
        if self.auto_audio is not None:
            try:
                self.auto_audio.terminate()
            except Exception:
                pass
            self.auto_audio = None

        self.auto_mode = False
        self.voice_button.setEnabled(True)
        self.source_combo.setEnabled(True)
        self.auto_button.setText("🤖 自动")
        self.auto_button.setStyleSheet(BUTTON_STYLE)
        self.realtime_label.hide()

    def _to_vad_frame(self, raw: bytes) -> bytes:
        """把任意采样率/声道的帧转成 20ms 16k 单声道 VAD 帧"""
        if self.auto_channels == 1 and self.auto_rate == 16000:
            return raw[:320]

        import array as _array
        samples = _array.array("h", raw)
        if self.auto_channels >= 2:
            samples = samples[::2]  # 取左声道
        step = max(1, round(self.auto_rate / 16000))
        samples = samples[::step]
        return samples[:320].tobytes()

    def _auto_tick(self):
        """每 20ms 轮询一次音频（非阻塞）：读走所有可用帧，累积后按 20ms 帧喂 VAD"""
        if self.auto_busy or not self.auto_mode or self.auto_stream is None:
            return
        self.auto_busy = True
        try:
            import time as _time

            # 非阻塞：只读当前已就绪的帧，避免设备无数据时 read 卡死界面
            try:
                available = self.auto_stream.get_read_available()
            except Exception:
                available = 0
            if available <= 0:
                return

            raw = self.auto_stream.read(available)
            self._auto_pcm += raw

            # 按 20ms 帧切分处理
            frame_bytes = self.auto_rate // 50 * self.auto_channels * 2
            while len(self._auto_pcm) >= frame_bytes:
                chunk = self._auto_pcm[:frame_bytes]
                self._auto_pcm = self._auto_pcm[frame_bytes:]

                if not self.is_recording and _time.monotonic() < self.auto_cooldown_until:
                    continue  # 停止后的冷却期，避免立即误触发

                action = self.auto_vad.feed(self._to_vad_frame(chunk))

                if action == "start":
                    self._auto_start_recording()
                elif action == "stop":
                    self._auto_stop_recording()

                if self.is_recording:
                    self.frames.append(chunk)
        except Exception as e:
            # 不静默吞异常：把问题显示出来，方便定位
            if self.auto_mode:
                self.realtime_label.setText(f"⚠️ 自动录音异常：{repr(e)[:80]}")
                self.realtime_label.show()
        finally:
            self.auto_busy = False

    def _auto_start_recording(self):
        """自动模式开始录音：复用监听流，只启动录音状态与流式识别"""
        self.is_recording = True
        self.frames = []
        self.stream_last_text = ""
        self.stream_gen += 1
        self.stream_busy = False
        self.realtime_label.setText("🔍 正在实时识别…")
        self.realtime_label.show()
        self.stream_timer.start()

    def _auto_stop_recording(self):
        """自动模式停止录音：先用最后的流式识别文本立即出答案，再后台完整识别兜底"""
        if not self.is_recording:
            return
        import time as _time
        self.is_recording = False
        self.stream_timer.stop()
        self.stream_gen += 1

        # 完整识别只保留最近 60 秒（问题通常远短于此），避免超长音频转写过慢
        frames_per_sec = self.auto_rate // 1024
        max_frames = frames_per_sec * 60
        frames = self.frames[-max_frames:] if len(self.frames) > max_frames else self.frames
        self._write_wav(self.output_filename, frames,
                        self.auto_rate, self.auto_channels, 2)
        self.frames = []

        self.auto_vad.reset()
        self.auto_cooldown_until = _time.monotonic() + 1.5
        if self.auto_mode:
            self.realtime_label.setText("🤖 自动监听中：说话自动开始，静音自动识别")
            self.realtime_label.show()

        if self.stream_last_text:
            # 最后 20 秒窗口的流式文本就是刚说完的问题：零等待直接出答案
            self._auto_pending_full = True
            self._handle_recognized_text(self.stream_last_text)
        # 后台完整识别兜底（音频更长时补全开头部分）
        self.on_recording_complete()

    @staticmethod
    def _texts_similar(a: str, b: str) -> bool:
        if not a or not b:
            return False
        a, b = a.strip(), b.strip()
        if a in b or b in a:
            return True
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio() > 0.7

    # ------------------------------------------------------------ 录音
    def toggle_recording(self):
        if self.is_recording:
            self.voice_button.setText("🎤 录音")
            self.stop_recording()
            self.realtime_label.hide()
        else:
            self.voice_button.setText("⏹ 停止")
            self.start_recording()

    def start_recording(self, stream=None, rate=None, channels=None, audio=None):
        """开始录音。手动模式自动打开音频流；自动模式复用监听流（传入 stream/audio）"""
        if self.is_recording:
            return
        self.chat_history.append("🎤 开始录音，再点一次停止并识别…")
        self.is_recording = True
        self.frames = []

        if stream is None:
            # 手动模式：按录音源自己开流
            dev = self.recording_sources[self.source_combo.currentIndex()]
            self.record_rate = int(dev["rate"])
            self.record_channels = int(dev["channels"])
            self.owns_stream = True

            self.audio = self._pa.PyAudio()
            kwargs = {
                "format": self._pa.paInt16,
                "channels": self.record_channels,
                "rate": self.record_rate,
                "input": True,
                "frames_per_buffer": 1024,
            }
            if dev["loopback_index"] is not None:
                kwargs["input_device_index"] = dev["loopback_index"]
            self.stream = self.audio.open(**kwargs)
        else:
            # 自动模式：复用监听流
            self.stream = stream
            self.audio = audio or self._pa.PyAudio()
            self.record_rate = int(rate or 16000)
            self.record_channels = int(channels or 1)
            self.owns_stream = False

        # 启动流式识别：边录音边识别边匹配
        self.stream_gen += 1
        self.stream_busy = False
        self.realtime_label.setText("🔍 正在实时识别…")
        self.realtime_label.show()
        self.stream_timer.start()

        self.record_audio()

    def record_audio(self):
        """持续录音（每 10ms 取一次数据）"""
        if self.is_recording:
            data = self.stream.read(1024)
            self.frames.append(data)
            QTimer.singleShot(10, self.record_audio)

    def _write_wav(self, path, frames, rate, channels, sample_width):
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(sample_width)
            wf.setframerate(rate)
            wf.writeframes(b"".join(frames))

    def _stream_recognize(self):
        """流式识别：把已录音频（最近 20 秒）送识别，新文本立即做知识库匹配"""
        if self.stream_busy or not self.is_recording:
            return
        frames_per_sec = self.record_rate // 1024
        if len(self.frames) < frames_per_sec:
            return  # 不足 1 秒

        self.stream_busy = True
        gen = self.stream_gen

        max_frames = frames_per_sec * STREAM_WINDOW_SECONDS
        frames = self.frames[-max_frames:] if len(self.frames) > max_frames else self.frames
        sample_width = self.audio.get_sample_size(self._pa.paInt16) if self.audio else 2

        tmp_path = ASSETS_DIR / "stream_tmp.wav"
        self._write_wav(tmp_path, frames, self.record_rate, self.record_channels, sample_width)

        def task():
            try:
                cfg = get_config()
            except Exception:
                cfg = {}
            r = whisper_speech_to_text_server(str(tmp_path), cfg)
            text = ""
            if isinstance(r, dict) and r.get("err_no") == 0 and r.get("result"):
                text = r["result"][0]
            kg = get_kg_answer(text) if text else []
            return (text, kg)

        t = TaskThread(task)
        t.result_signal.connect(lambda res, g=gen: self._on_stream_result(g, res))
        t.finished_signal.connect(lambda th=t: self._cleanup_thread(th))
        self.active_threads.append(t)
        t.start()

    def _on_stream_result(self, gen, result):
        self.stream_busy = False
        if gen != self.stream_gen or not self.is_recording:
            return  # 已停止录音，丢弃在途的流式结果
        text, kg = result
        if not text:
            return
        self.stream_last_text = text
        display = "🔍 实时识别：" + text
        if kg:
            display += f"　📚 候选：{kg[0][0][:36]}"
        self.realtime_label.setText(display)

    def stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False

        # 停止流式识别，作废在途结果；随后做完整的最终识别（与流式匹配并行互补）
        self.stream_timer.stop()
        self.stream_gen += 1

        sample_width = self.audio.get_sample_size(self._pa.paInt16)

        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            if self.owns_stream:
                self.audio.terminate()

        self._write_wav(self.output_filename, self.frames,
                        self.record_rate, self.record_channels, sample_width)

        self.frames = []
        self.stream = None
        self.audio = None

        self.chat_history.append("录音已保存，正在识别…")
        self.on_recording_complete()

    def on_recording_complete(self):
        """后台线程做语音识别，避免界面卡住"""
        asr_thread = TaskThread(speech_to_text, self.output_filename)
        asr_thread.result_signal.connect(self.handle_asr_result)
        asr_thread.finished_signal.connect(
            lambda t=asr_thread: self._cleanup_thread(t)
        )
        self.active_threads.append(asr_thread)
        asr_thread.start()

    def handle_asr_result(self, result):
        if not isinstance(result, dict):
            self.chat_history.append(f"语音识别返回异常：{result}")
            return

        if result.get("err_no") != 0:
            self.chat_history.append(f"语音识别失败：{result.get('err_msg', '未知错误')}")
            return

        raw_text = result.get("result", [""])[0]
        recognized_text = normalize_interview_text(raw_text)

        # 自动模式：完整识别是流式文本的兜底校验，内容一致时不重复出答案
        if self._auto_pending_full and self._texts_similar(recognized_text, self.stream_last_text):
            self._auto_pending_full = False
            if len(recognized_text) > len(self.stream_last_text) * 1.3:
                # 完整识别明显更完整（长音频补全了开头），用它重新出答案
                self.chat_history.append("（完整识别补充了更多内容，更新答案）")
                self._handle_recognized_text(recognized_text)
            else:
                self.chat_history.append("（完整识别与实时识别一致）")
            return
        self._auto_pending_full = False

        self._handle_recognized_text(recognized_text)

    def _handle_recognized_text(self, recognized_text):
        """识别文本的统一处理：知识库匹配 + 大模型回答"""
        self.chat_history.append(f"你（语音）：{recognized_text}\n")

        if self.kg_check.isChecked():
            kg_results = get_kg_answer(recognized_text)
            if kg_results:
                self.show_kg_results_compact(kg_results)
            else:
                self.chat_history.append("（本地题库未命中，改用大模型回答）")

        self.ask_ai_answer(recognized_text)

    # ------------------------------------------------------------ 通用提示
    def show_popup_message(self, title, message):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText(message)
        msg.setWindowTitle(title)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
