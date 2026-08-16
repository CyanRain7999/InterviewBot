from PyQt5.QtCore import QThread, pyqtSignal


class StreamTaskThread(QThread):
    chunk_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, stream_func, *args):
        super().__init__()
        self.stream_func = stream_func
        self.args = args

    def run(self):
        try:
            for chunk in self.stream_func(*self.args):
                if chunk:
                    self.chunk_signal.emit(str(chunk))
        except Exception as e:
            self.error_signal.emit(f"流式生成失败：{repr(e)}")
        finally:
            self.finished_signal.emit()