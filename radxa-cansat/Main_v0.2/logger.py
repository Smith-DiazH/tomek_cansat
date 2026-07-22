 #!/usr/bin/env python3
import threading
import queue
import time
import os

LOG_FILE = "registro_telemetria.txt"

class LogWriter(threading.Thread):
    def __init__(self, log_q: queue.Queue, file_path=LOG_FILE):
        super().__init__(daemon=True, name="LogWriter")
        self.log_q     = log_q
        self.file_path = file_path
        self._stop     = False

    def solicitar_parada(self):
        self._stop = True

    def run(self):
        print(f"[Logger] Guardando en: {os.path.abspath(self.file_path)}")
        while not self._stop or not self.log_q.empty():
            try:
                linea = self.log_q.get(timeout=0.5)
                ts    = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(f"[{ts}] {linea}\n")
                self.log_q.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                print(f"[Logger] Error: {e}")
