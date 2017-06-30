from multiprocessing import Process
class PBProcess:
    def __init__(self, target, *args, **kwargs):
        self._proc = Process(target=target, args=args, kwargs=kwargs)
        self._started = False

    def start(self):
        self._started = True
        self._proc.start()
        return self

    def is_alive(self):
        return self._started
