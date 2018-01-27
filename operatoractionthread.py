import time
from queue import Empty, Queue
from random import randint
from time import sleep, time
from threading import Event, Timer
from pbthread import PBThread
from outboundmessagethread import OutboundMessageThread

class OperatorActionThread(PBThread):
    def __init__(self, global_state):
        PBThread.__init__(self, self._enter, name='OperatorAction')
        self._is_op = Event()
        self._waiting_actions = Queue(100)
        self._unmute_timer = None
        self._last_mute = 0.1
        self.update_global_state(global_state)

    def update_global_state(self, gs):
        self._log = gs['log']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        self._out_msg = gs['threads']['out_message']

    def _enter(self):
        log = self._log
        log.notice('Started OperatorActionThread instance')
        log.debug('OperatorActionThread: Asking to be deopped')
        self._out_msg.add(self._out_msg.privmsg,
            ['chanserv', 'deop {} kist'.format(
            self._conf['ii']['channel'])])
        while not self._is_shutting_down.is_set():
            while not (self._is_op.wait(1) or self._is_shutting_down.is_set()):
                pass
            if self._is_shutting_down.is_set(): break
            item = None
            count_empty, max_empty = 0, randint(120,180)
            log.debug('OperatorActionThread: waiting {}s for an action'.format(
                max_empty))
            while count_empty < max_empty and\
                not self._is_shutting_down.is_set():
                try: item = self._waiting_actions.get(timeout=1.0)
                except Empty: count_empty += 1
                else: break
            if self._is_shutting_down.is_set(): break
            if not item:
                log.debug('OperatorActionThread: no item')
                if self._is_op.is_set():
                    log.debug('OperatorActionThread: Asking to be deopped')
                    self._out_msg.add(self._out_msg.privmsg,
                        ['chanserv', 'deop {} kist'.format(
                        self._conf['ii']['channel'])])
                    sleep(1.0)
                continue
            args, kwargs = item
            #log.debug('OperatorActionThread: item: {} {}'.format(args, kwargs))
            self._out_msg.add(*args, **kwargs)
        self._shutdown()

    def _shutdown(self):
        log = self._log
        log.notice('OperatorActionThread going away')

    def recv_action(self, *args, **kwargs):
        if not self._is_op.is_set():
            log = self._log
            log.debug('OperatorActionThread: Asking to be opped')
            self._out_msg.add(self._out_msg.privmsg,
                ['chanserv', 'op {} kist'.format(
                    self._conf['ii']['channel'])])
        self._waiting_actions.put( (args, kwargs) )
        #print(args, kwargs)

    def temporary_mute(self, enabled=True):
        log = self._log
        out_msg = self._out_msg
        channel_name = self._conf['ii']['channel']
        if enabled and self._last_mute + 5 < time():
            log.info('Muting channel')
            self._last_mute = time()
            self.recv_action(out_msg.servmsg,
                ['/mode {} +RM'.format(channel_name)])
            # Doesn't seem to help/work
            #if self._unmute_timer and self._unmute_timer.is_alive():
            #    log.debug('Killing previous unmute timer')
            #    self._unmute_timer.cancel()
            #    self._unmute_timer = None
            log.info('Starting an unmute timer')
            self._unmute_timer = Timer(randint(45,75),
                self.temporary_mute,
                kwargs={'enabled': False}).start()
        elif not enabled:
            log.info('Unmute timer done. Unmuting')
            self.recv_action(out_msg.servmsg,
                ['/mode {} -RM'.format(channel_name)])

    def set_chan_mode(self, mode_str, reason):
        log = self._log
        out_msg = self._out_msg
        channel_name = self._conf['ii']['channel']
        log.info('Setting channel mode {} because {}'.format(mode_str, reason))
        self.recv_action(out_msg.servmsg,
            ['/mode {} {}'.format(channel_name, mode_str)])

    def kick_nick(self, nick):
        log = self._log
        out_msg = self._out_msg
        log.info('Kicking {}'.format(nick))
        channel_name = self._conf['ii']['channel']
        self.recv_action(out_msg.servmsg,
                ['/kick {} {}'.format(channel_name, nick)])

    def set_opped(self, opped):
        log = self._log
        if opped: self._is_op.set()
        else: self._is_op.clear()
        log.notice('We have been {}'.format("opped" if opped else "deopped"))
