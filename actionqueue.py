import signal
from time import sleep, time
from queue import Empty, PriorityQueue
from multiprocessing import Event, Process, Queue
class ActionQueue:

    # time_between_actions is a number of seconds (with optional fractional
    # part) that must elapse between individual actions are processed out of
    # the priority queue. A time of 0 means no time must pass and to process
    # actions as quickly as possible.
    def __init__(self, time_between_actions=0):
        self._incoming_queue = Queue()
        self._action_queue = PriorityQueue()
        self._time_between_actions = time_between_actions
        # timestamp at which the last action was taken
        self._last_action = 0
        # number of seconds to wait for a new action to come in via
        # self.add(...) when we have no actions in the priority queue
        # this also affects how quickly we exit loop_once when there's nothing
        # to do, and thus how quickly we can react to shutting down
        self._long_timeout = 1.0


    # This function should be called by the main process to add an action to
    # this process's priority queue through this inter-process FIFO.
    # - func is the function to call in this process
    # - args is an optional list of arguments to pass to the function
    # - priority is ... the priority. Obviously. This is a min-priority queue.
    #   thus a smaller priority means a "better" priority and that item should
    #   be handled more quickly. By default, priority is the current time (in
    #   seconds, and probably with fractional seconds). To put something in the
    #   queue with a little extra importance (like 5 seconds worth), set
    #   priority to time()-5. To put something in with upmost priority, add it
    #   with priority == 0. If you never specify a priority, then this structure
    #   is essentially a FIFO queue in its own process.
    def add(self, func, args=None, priority=None):
        if priority == None: priority = time()
        self._incoming_queue.put( (priority, (func, args)) )

    def __process_incoming_queue(self, timeout):
        try: item = self._incoming_queue.get(timeout=timeout)
        except Empty: item = None
        if item != None:
            self._action_queue.put(item)

    def loop_once(self):
        # first make sure enough time has passed since our last action
        if time() - self._last_action >= self._time_between_actions:
            # get an action out of the priority queue
            try: item = self._action_queue.get_nowait()
            except Empty: item = None
            # if we got one, then handle it
            if item != None:
                # item comes in as (priority, (func, [argA, argB]) )
                func, args = item[1]
                #item = item[1]
                #func = item[0]
                #args = item[1]
                if args == None: func()
                else: func(*args)
                self._last_action = time()

        # now we have handled zero or one actions from the priority queue and
        # are done with it. Now we should see if there are any more actions to
        # add to the priority queue waiting on the incoming queue.

        # if there is nothing in the priority queue, we can afford to wait for
        # a new action to come in for a long time.
        if self._action_queue.empty():
            self.__process_incoming_queue(timeout=self._long_timeout)
        # if there is another action waiting in the priority queue, we can only
        # afford to wait for the remaining time_between_actions
        else:
            timeout = (self._last_action - time()) + self._time_between_actions
            if timeout < 0: timeout=0
            self.__process_incoming_queue(timeout=timeout)
