from queue import Empty, Queue
from random import randint
from time import sleep, time
from threading import Event, Timer
from pbthread import PBThread


class OperatorActionThread(PBThread):
    def __init__(self, global_state, channel_name):
        PBThread.__init__(self, self._enter,
                          name='OperatorAction-{}'.format(channel_name))
        self._is_op = Event()
        self._waiting_actions = Queue(100)
        self._unmute_timer = None
        self._last_mute = 0.1
        self._channel_name = channel_name
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._out_msg = gs['threads']['out_message']
        self._heart_thread = gs['threads']['heart']

    def _enter(self):
        log = self._log
        log.info('Started OperatorActionThread instance')
        log.debug('Asking to be deopped')
        channel_name = self._channel_name
        self._out_msg.add(self._out_msg.privmsg,
                          ['chanserv', 'deop {} kist'.format(channel_name)])
        while not self._is_shutting_down.is_set():
            while not (self._is_op.wait(1) or self._is_shutting_down.is_set()):
                pass
            if self._is_shutting_down.is_set():
                break
            item = None
            count_empty, max_empty = 0, randint(120, 180)
            log.debug('waiting {}s for an action'.format(max_empty))
            while count_empty < max_empty and \
                    not self._is_shutting_down.is_set():
                try:
                    item = self._waiting_actions.get(timeout=1.0)
                except Empty:
                    count_empty += 1
                else:
                    break
            if self._is_shutting_down.is_set():
                break
            if not item:
                log.debug('no item')
                if self._is_op.is_set():
                    log.debug('Asking to be deopped')
                    self._out_msg.add(
                        self._out_msg.privmsg,
                        ['chanserv', 'deop {} kist'.format(channel_name)])
                    sleep(1.0)
                continue
            args, kwargs = item
            # log.debug('item: {} {}'.format(args, kwargs))
            self._out_msg.add(*args, **kwargs)
        self._shutdown()

    def _shutdown(self):
        log = self._log
        log.info('OperatorActionThread going away')

    def recv_action(self, *args, **kwargs):
        ''' Call from other threads. '''
        if not self._is_op.is_set():
            log = self._log
            log.debug('Asking to be opped in channel', self._channel_name)
            self._out_msg.add(
                self._out_msg.privmsg,
                ['chanserv', 'op {} kist'.format(self._channel_name)])
        self._waiting_actions.put((args, kwargs))

    def temporary_mute(self, enabled=True):
        ''' Call from other threads. '''
        log = self._log
        if enabled and self._last_mute + 5 < time():
            log.info('Muting channel')
            self._last_mute = time()
            self.set_chan_mode('+RM', 'temporary mute')
            log.info('Starting an unmute timer')
            self._unmute_timer = Timer(
                randint(120, 300),
                self.temporary_mute,
                kwargs={'enabled': False}).start()
        elif not enabled:
            log.info('Unmute timer done. Unmuting')
            self.set_chan_mode('-RM', 'end of temporary mute')

    def set_chan_mode(self, mode_str, reason):
        ''' Call from other threads. '''
        log = self._log
        out_msg = self._out_msg
        log.notice(
            'Setting channel mode', mode_str, 'on', self._channel_name,
            'because', reason)
        self._heart_thread.event_set_mode()
        self.recv_action(
            out_msg.add,
            [out_msg.servmsg,
             ['/mode {} {}'.format(self._channel_name, mode_str)]])

    def kick_nick(self, nick, reason):
        ''' Call from other threads. '''
        log = self._log
        out_msg = self._out_msg
        log.notice(
            'Kicking', nick, 'from', self._channel_name, 'because', reason)
        self._heart_thread.event_kick()
        self.recv_action(
            out_msg.add,
            [out_msg.servmsg,
             ['/kick {} {} :{}'.format(self._channel_name, nick, reason)]])

    def set_opped(self, opped):
        log = self._log
        if opped:
            self._is_op.set()
        else:
            self._is_op.clear()
        log.info('We have been {}'.format("opped" if opped else "deopped"))
