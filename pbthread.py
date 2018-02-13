from threading import Thread


class PBThread:
    # All children of PBThread should have an __init__ that calls
    # this as the very first thing
    def __init__(self, target, *args, name=None, **kwargs):
        self._thread = Thread(target=target, args=args, kwargs=kwargs,
                              name=name)
        self._started = False
        self._gs = None

    # This should probably NOT be reimplemented in children. It starts the
    # thread.
    def start(self):
        self._started = True
        self._thread.start()
        return self

    # This should probably NOT be reimplemented in children.
    def is_alive(self):
        return self._started

    # This should probably NOT be reimplemented in children.
    def join(self, timeout=None):
        return self._thread.join(timeout=timeout)

    # This probably SHOULD be reimplemented in children. Instead of using a _gs
    # member, it would be smarter to only pull the things out of the global
    # state that the class actually uses. Therefore, reimplement this.
    def update_global_state(self, gs):
        print('PBThread update_global_state')
        self._gs = gs
