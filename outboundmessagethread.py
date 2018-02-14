import os
from pbthread import PBThread
from actionqueue import ActionQueue


class OutboundMessageThread(PBThread):
    ''' If the bot is going to send a message/command to the IRC server, it
    must do so through this class.

    Use the add() function to add an outbound message/command. For example, to
    privmsg the user 'pastly':

    >>> omt = outbound_message_thread
    >>> omt.add(omt.privmsg, ['pastly', 'I dont like sand'])

    More generally, specify the function you want to call as the first argument
    to add(), any arguments you want to pass to it in as a list, and finally
    any keyword arguments you want to pass to it as a dictionary.
    '''

    def __init__(self, global_state,
                 long_timeout=5, time_between_actions_func=None):
        PBThread.__init__(self, self._enter, name='OutboundMessage')
        self._action_queue = \
            ActionQueue(long_timeout=long_timeout,
                        time_between_actions_func=time_between_actions_func)
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._conf = gs['conf']
        self._server_dir = os.path.join(
            gs['conf']['ii']['ircdir'], gs['conf']['ii']['server'])
        self._end_event = gs['events']['kill_outmessage']

    def _enter(self):
        log = self._log
        log.info('Started OutboundMessageThread instance')
        while not self._end_event.is_set():
            self._action_queue.loop_once()
        self._shutdown()

    def _shutdown(self):
        log = self._log
        log.info('OutboundMessageThread going away')

    def add(self, *args, **kwargs):
        ''' Use this function to add outbound messages/commands '''
        self._action_queue.add(*args, **kwargs)

    def servmsg(self, message):
        ''' Do not call this function directly. Pass it as an argument to add()

        >>> omt = outbound_message_thread
        >>> omt.add(omt.servmsg, ['/mode #foo +i'])
        '''
        fname = os.path.join(self._server_dir, 'in')
        with open(fname, 'w') as server_in:
            server_in.write('{}\n'.format(message))

    def privmsg(self, nick, message):
        ''' Do not call this function directly. Pass it as an argument to add()

        >>> omt = outbound_message_thread
        >>> omt.add(omt.privmsg, ['pastly', 'You left the stove on'])
        '''
        self.servmsg('/privmsg {} {}'.format(nick, message))

    def notice(self, target, message):
        ''' Do not call this function directly. Pass it as an argument to add()

        >>> omt = outbound_message_thread
        >>> omt.add(omt.notice, ['#foobar', 'Promise this isnt spam'])
        '''
        self.servmsg('/notice {} {}'.format(target, message))
