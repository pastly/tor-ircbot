import os
import random
from pbthread import PBThread
from actionqueue import ActionQueue

class OutboundMessageThread(PBThread):
    pong_msgs = [ 'pong', 'PONG', 'POOOONG!!!!', 'JFC pong', 'No. Just stop.',
        'WTF do you want from me?', 'I\'m busy', 'moo', 'ACK', 'RST',
        'You\'re not the boss of me.'
    ]
    def __init__(self, global_state,
        long_timeout=5, time_between_actions_func=None):
        PBThread.__init__(self, self._enter, name='OutboundMessage')
        self._action_queue = ActionQueue(long_timeout=long_timeout,
            time_between_actions_func=time_between_actions_func)
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._conf = gs['conf']
        self._server_dir = os.path.join(
            gs['conf']['ii']['ircdir'], gs['conf']['ii']['server'])
        self._is_shutting_down = gs['events']['is_shutting_down']

    def _enter(self):
        log = self._log
        log.notice('Started OutboundMessageThread instance')
        while not self._is_shutting_down.is_set():
            self._action_queue.loop_once()
        self._shutdown()

    def _shutdown(self):
        log = self._log
        log.notice('OutboundMessageThread going away')

    def add(self, *args, **kwargs):
        self._action_queue.add(*args, **kwargs)

    def servmsg(self, message):
        fname = os.path.join(self._server_dir, 'in')
        with open(fname, 'w') as server_in:
            server_in.write('{}\n'.format(message))

    def privmsg(self, nick, message):
        self.servmsg('/privmsg {} {}'.format(nick, message))

    def pong(self, nick):
        self.privmsg(nick, random.choice(OutboundMessageThread.pong_msgs))
