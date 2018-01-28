import signal
from time import time
from queue import Empty, PriorityQueue, Queue
class ActionQueue:
    ''' A priority queue of functions to call in a controlling thread's main
    loop.

    Add functions to call with add(), optionally with arguments and/or keyword
    arguments. A priority may also be specified. Lower priority items will be
    handled first.

    The controlling thread should repeatedly call loop_once(), most likely in a
    (near) infinite main loop. It is up to the controlling thread to realize
    if/when it is time to shutdown and quit. '''

    def __init__(self, long_timeout=10, time_between_actions_func=None):
        ''' long_timeout is how long loop_once() will block when there is
        nothing to do.

        time_between_actions_func is a function called after every action to
        determine how long we must wait before executing another action. The
        function must take one argument: a variable holding its state. It
        must return a tuple: (time_to_wait, new_state). '''
        self._incoming_queue = Queue()
        self._action_queue = PriorityQueue()
        # A function pointer that is called after every action to caclulate
        # the amount of time to wait before executing the next action in the
        # priority queue. The function takes one argument, a variable for
        # holding state. It returns a tuple: (time_to_wait, new_state). If the
        # function needs to keep track of some information between calls, it
        # should use the state variable.
        if time_between_actions_func:
            self._time_between_actions_func = time_between_actions_func
        else:
            self._time_between_actions_func = \
                ActionQueue.__default_time_between_actions_func
        self._time_between_actions_func_state = None
        # timestamp at which we can perform another action, as calculated by
        # the current time + return value from time_between_actions_func
        self._next_action = 0
        # Number of seconds to wait for a new action to come in via
        # self.add(...) when we have no actions in the priority queue.
        # Too low, and we hurt CPU by abusively busy waiting.
        # Too high, and we don't react to the controlling process wanting to
        # shut down very quickly
        self._long_timeout = long_timeout

    # This function should be called by the main thread to add an action to
    # this thread's priority queue through this inter-thread FIFO.
    # - func is the function to call in this thread
    # - args is an optional list of arguments to pass to the function
    # - kwargs is an optional dictionary of arguments to pass to the function
    # - priority is ... the priority. Obviously. This is a min-priority queue.
    #   Thus a smaller priority means a "better" priority and that item should
    #   be handled more quickly. By default, priority is the current time (in
    #   seconds, and probably with fractional seconds). To put something in the
    #   queue with a little extra importance (like 5 seconds worth), set
    #   priority to time()-5. To put something in with upmost priority, add it
    #   with priority == 0. If you never specify a priority, then this
    #   ActionQueue is essentially a FIFO queue in its own thread. NOTE: while
    #   priority defaults to time, that does NOT mean setting
    #   priority == time()+5 means the item will be processed after 5 seconds.
    def add(self, func, args=None, kwargs=None, priority=None):
        if priority == None: priority = time()
        self._incoming_queue.put( (priority, (func, args, kwargs)) )

    # A very simple time_between_actions_func that instructs the ActionQueue
    # to not wait at all between actions. All time_between_actions_func's must
    # take a state argument and return the new state. This is how you would
    # write one that doesn't need any state.
    def __default_time_between_actions_func(state):
        return 0, None

    def __process_incoming_queue(self, timeout):
        try: item = self._incoming_queue.get(timeout=timeout)
        except Empty: item = None
        if item != None:
            self._action_queue.put(item)

    def loop_once(self):
        time_to_wait = None

        # first make sure enough time has passed since our last action
        if time() >= self._next_action:
            # get an action out of the priority queue
            try: item = self._action_queue.get_nowait()
            except Empty: item = None
            # if we got one, then handle it
            if item != None:
                # item comes in as (priority, (func, args=[], kwargs={}) )
                func, args, kwargs = item[1]
                if args == None and kwargs == None: func()
                elif args and kwargs == None: func(*args)
                elif kwargs and args == None: func(**kwargs)
                else: func(*args, **kwargs)
                # now run the _time_between_actions_func to determine how long
                # we must wait before processing another event
                old_state = self._time_between_actions_func_state
                time_to_wait, new_state = \
                    self._time_between_actions_func(old_state)
                self._time_between_actions_func_state = new_state
                self._next_action = time() + time_to_wait

        # Now we have handled zero or one actions from the priority queue and
        # are done with it for this loop. We should see if there are any more
        # actions in the incoming queue to add to the priority queue.

        # if there is nothing in the priority queue, we can afford to wait a
        # long time for a new action to come in.
        if self._action_queue.empty():
            self.__process_incoming_queue(timeout=self._long_timeout)
        # if there is another action waiting in the priority queue, we can only
        # afford to wait for the remaining time until we should perform it
        else:
            timeout = self._next_action - time()
            if timeout < 0: timeout=0
            self.__process_incoming_queue(timeout=timeout)
