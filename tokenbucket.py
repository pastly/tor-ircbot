from time import time
# Return a function that implements a token bucket of sorts.
#
# The returned function is intended to be called once immediately after every
# action that consumes a token.
#
# The two arguments to this function are the size of the token bucket (maximum
# number of tokens it can hold), and the rate at which the bucket refills with
# tokens (number of seconds between each additional earned token).
#
# Concerning the generated tocket bucket function:
#
# The function relies on the caller to keep track of its state.
#
# It takes one argument: its previous state
# It returns two values:
# - the amount of time that must be waited before performing another action; and
# - its new state
def token_bucket(size_, refill_rate_):

    def closure_token_bucket(state):
        size = size_
        refill_rate = refill_rate_
        # If no state yet, initialize it.
        if not state: state = {
            'tokens': size,
            'last_action': 0,
        }
        # By calling this function, we know we have performed an action and must
        # therefore spend a token
        state['tokens'] -= 1
        # Now calculate how many more tokens we can give ourselves based on how
        # much time has passed since the last action
        now = time()
        time_since_last_action = now - state['last_action']
        state['last_action'] = now
        # Gives ourselves more tokens until
        # - we hit the max; or
        # - haven't earned any more
        while state['tokens'] < size-1 and time_since_last_action > refill_rate:
            state['tokens'] += 1
            time_since_last_action -= refill_rate
        if state['tokens'] > 0:
            return 0, state
        else:
            return refill_rate, state

    return closure_token_bucket
