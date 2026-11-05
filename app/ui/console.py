"""Adaptador thread-safe de stdout/stderr a la consola gráfica."""
import queue


class RedirectConsole:
    """Redirige stdout y stderr hacia una cola segura para hilos (Thread-safe)."""
    def __init__(self, log_queue: queue.Queue, original_stream):
        self.log_queue = log_queue
        self.original_stream = original_stream

    def write(self, message: str):
        if self.original_stream:
            try:
                self.original_stream.write(message)
            except Exception:
                pass
        if message:
            self.log_queue.put(message)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass
