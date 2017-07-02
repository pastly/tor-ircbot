from multiprocessing import Process
class PBProcess:
    # All children of PBProcess should have an __init__ that calls
    # this as the very first thing
    def __init__(self, target, *args, **kwargs):
        self._proc = Process(target=target, args=args, kwargs=kwargs)
        self._started = False
        self._gs = None

    # This should probably NOT be reimplemented in children. It starts the
    # process.
    def start(self):
        self._started = True
        self._proc.start()
        return self

    # This should probably NOT be reimplemented in children. Since
    # multiprocessing.Process has an is_alive() func, I thought I should too.
    def is_alive(self):
        return self._started

    # This probably SHOULD be reimplemented in children. Instead of using a _gs
    # member, it would be smarter to only pull the things out of the global
    # state that the class actually uses. Therefore, reimplement this.
    def update_global_state(self, gs):
        print('PBProcess update_global_state')
        self._gs = gs
