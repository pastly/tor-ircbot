from time import sleep, time
from queue import Empty
class ActionQueue:
    def __init__(self, queue, max_speed=0):
        self._q = queue
        self._max_speed = max_speed
        self._last_action = 0
        self._shutting_down = False

    # - func is the function to call when handling this item
    # - args are a list of arguments to pass to that function
    # - priority is ... the priority. Obviously. This is a min-priority queue.
    #   thus a smaller priority means a "better" priority and that item should
    #   be handled more quickly. By default, priority is the current time (in
    #   seconds, and probably with fractional seconds). To put something in the
    #   queue with a little extra importance (like 5 seconds worth), set
    #   priority to time()-5. To put something in with upmost priority, add it
    #   with priority == 0. If you never specify a priority, then this is
    #   essentially a FIFO.
    def add(self, func, args=None, priority=None):
        if self._shutting_down: return
        if priority == None: priority = time()
        self._q.put( (priority, (func, args)) )

    def process(self, timeout=None):
        if timeout == None: timeout = self._max_speed / 2
        while True:
            try: item = self._q.get(timeout=timeout)
            except Empty: break
            now = time()
            timediff = now - self._last_action
            if timediff < self._max_speed: sleep(self._max_speed - timediff)
            item = item[1]
            func, args = item
            if args == None: func()
            else: func(*args)
            self._last_action = time()

    # called from the main thread to clear out the queue so no more events
    # will be handled and the message queue thread can timeout
    def self_destruct(self):
        self._shutting_down = True
        while True:
            try: self._q.get_nowait()
            except Empty: break
