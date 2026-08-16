# -*- coding: utf-8 -*-
"""
自动录音的语音活动检测（VAD）状态机。
- 静音中检测到持续语音 -> 返回 "start"（开始录音）
- 录音中检测到持续静音 -> 返回 "stop"（停止录音）
- 其他情况返回 "continue" / "ignore"

基于 webrtcvad（WebRTC 语音活动检测），帧格式：20ms、16kHz、单声道、16bit PCM。
"""
try:
    import webrtcvad
except ImportError:
    webrtcvad = None

# 判定"开始说话"需要的连续有声帧数（80ms @20ms/帧）
VOICE_START_FRAMES = 4
# 判定"说话结束"需要的连续静音帧数（2.5s @20ms/帧）
# 调大可容忍对方思考停顿；调小则更快出结果
SILENCE_STOP_FRAMES = 125
# 能量下限：低于此值直接视为静音（配合 VAD 双保险）
ENERGY_THRESHOLD = 150

FRAME_BYTES = 320  # 20ms @ 16kHz 单声道 16bit


class AutoVad:
    def __init__(self, mode=1, silence_stop_frames=SILENCE_STOP_FRAMES):
        """mode: webrtcvad 灵敏度 0-3（0 最宽松，3 最严格）
        silence_stop_frames: 连续静音多少帧判定说话结束（20ms/帧）"""
        self.mode = mode
        self.silence_stop_frames = silence_stop_frames
        self.vad = webrtcvad.Vad(mode) if webrtcvad else None
        self.speaking = False
        self.voiced_run = 0
        self.silence_run = 0

    def reset(self):
        self.speaking = False
        self.voiced_run = 0
        self.silence_run = 0

    @staticmethod
    def energy(frame: bytes) -> float:
        """计算 RMS 能量"""
        if not frame:
            return 0.0
        samples = frame[::2]  # 低字节
        if not samples:
            return 0.0
        total = 0
        for b in samples:
            total += b * b
        return (total / len(samples)) ** 0.5

    def feed(self, frame: bytes):
        """
        喂一帧 20ms 音频，返回动作：
        "start"  -> 开始录音
        "stop"   -> 停止录音
        "continue" -> 录音中（无状态变化）
        "ignore" -> 监听中（无状态变化）
        """
        if len(frame) < FRAME_BYTES:
            return "ignore"

        frame = frame[:FRAME_BYTES]

        # 能量双保险：明显静音直接判无声
        if self.energy(frame) < ENERGY_THRESHOLD:
            is_speech = False
        elif self.vad is not None:
            try:
                is_speech = self.vad.is_speech(frame, 16000)
            except Exception:
                is_speech = False
        else:
            # 没有 webrtcvad 时退化为纯能量检测
            is_speech = self.energy(frame) > ENERGY_THRESHOLD * 2

        if not self.speaking:
            # 监听中：连续有声帧达到阈值 -> 开始录音
            self.voiced_run = self.voiced_run + 1 if is_speech else 0
            if self.voiced_run >= VOICE_START_FRAMES:
                self.speaking = True
                self.silence_run = 0
                return "start"
            return "ignore"

        # 录音中
        if is_speech:
            self.silence_run = 0
            return "continue"

        self.silence_run += 1
        if self.silence_run >= self.silence_stop_frames:
            self.speaking = False
            self.voiced_run = 0
            return "stop"

        return "continue"
