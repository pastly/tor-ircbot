import signal
def add_current_signals_to_stack(stack):
    stack.append(signal.getsignal(signal.SIGINT))
    stack.append(signal.getsignal(signal.SIGTERM))
    stack.append(signal.getsignal(signal.SIGHUP))
    return stack

def pop_signals_from_stack(stack):
    stack.pop()
    stack.pop()
    stack.pop()
    signal.signal(signal.SIGINT, stack[-3])
    signal.signal(signal.SIGTERM, stack[-2])
    signal.signal(signal.SIGHUP, stack[-1])
    return stack

#def get_current_signals(stack):
#    return stack[-3:]

def get_default_signals(stack):
    return stack[0:3]

def set_signals(stack, INT, TERM, HUP):
    signal.signal(signal.SIGINT, INT)
    signal.signal(signal.SIGTERM, TERM)
    signal.signal(signal.SIGHUP, HUP)
    return add_current_signals_to_stack(stack)

