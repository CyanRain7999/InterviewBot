from PyQt5.QtCore import QThread, pyqtSignal


class TaskThread(QThread):
    result_signal = pyqtSignal(object)
    finished_signal = pyqtSignal()

    def __init__(self, task_func, *args):
        super().__init__()
        self.task_func = task_func
        self.args = args

    def run(self):
        try:
            result = self.task_func(*self.args)
            self.result_signal.emit(result)
        except Exception as e:
            self.result_signal.emit({
                "err_no": -999,
                "err_msg": f"TaskThread 执行失败：{repr(e)}",
                "result": []
            })
        finally:
            self.finished_signal.emit()
