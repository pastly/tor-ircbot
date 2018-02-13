from pbthread import PBThread
from queue import Empty, Queue
from enum import Enum
import time


def seconds_to_duration(secs):
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    d, h, m, s = int(d), int(h), int(m), int(round(s, 0))
    if d > 0:
        return '{}d{}h{}m{}s'.format(d, h, m, s)
    elif h > 0:
        return '{}h{}m{}s'.format(h, m, s)
    elif m > 0:
        return '{}m{}s'.format(m, s)
    else:
        return '{}s'.format(s)


class HeartbeatThread(PBThread):

    class HBEvent(Enum):
        ADD_NICK = 1
        CHANGE_NICK = 2
        DEL_NICK = 3
        QUIET_ADD = 4
        AKICK_ADD = 5
        QUIET_DEL = 6
        AKICK_DEL = 7
        SET_MODE = 8
        KICK = 9
        CHAN_MSG = 10

    def __init__(self, global_state):
        PBThread.__init__(self, self._enter, name='Heartbeat')
        self._event_queue = Queue(10)
        self._start = time.time()
        self._counters = {
            'add_nick': 0, 'add_nick_total': 0,
            'change_nick': 0, 'change_nick_total': 0,
            'del_nick': 0, 'del_nick_total': 0,
            'quiet_add': 0, 'quiet_add_total': 0,
            'quiet_del': 0, 'quiet_del_total': 0,
            'akick_add': 0, 'akick_add_total': 0,
            'akick_del': 0, 'akick_del_total': 0,
            'mode': 0, 'mode_total': 0,
            'kick': 0, 'kick_total': 0,
            'chan_msg': 0, 'chan_msg_total': 0,
        }

        self.update_global_state(global_state)

    def _enter(self):
        log = self._log
        log.info('Starting Heartbeatthread instance')
        while not self._is_shutting_down.is_set():
            event = None
            try:
                event = self._event_queue.get(timeout=1)
            except Empty:
                if self._is_shutting_down.is_set():
                    return self._shutdown()
            if event is not None:
                self._handle_event(event)
            if self._should_log_heartbeat():
                self._log_heartbeat()

    def _handle_event(self, event):
        assert isinstance(event, HeartbeatThread.HBEvent)
        counters = self._counters
        if event == HeartbeatThread.HBEvent.ADD_NICK:
            counters['add_nick'] += 1
            counters['add_nick_total'] += 1
        elif event == HeartbeatThread.HBEvent.CHANGE_NICK:
            counters['change_nick'] += 1
            counters['change_nick_total'] += 1
        elif event == HeartbeatThread.HBEvent.DEL_NICK:
            counters['del_nick'] += 1
            counters['del_nick_total'] += 1
        elif event == HeartbeatThread.HBEvent.QUIET_ADD:
            counters['quiet_add'] += 1
            counters['quiet_add_total'] += 1
        elif event == HeartbeatThread.HBEvent.AKICK_ADD:
            counters['akick_add'] += 1
            counters['akick_add_total'] += 1
        elif event == HeartbeatThread.HBEvent.QUIET_DEL:
            counters['quiet_del'] += 1
            counters['quiet_del_total'] += 1
        elif event == HeartbeatThread.HBEvent.AKICK_DEL:
            counters['akick_del'] += 1
            counters['akick_del_total'] += 1
        elif event == HeartbeatThread.HBEvent.SET_MODE:
            counters['mode'] += 1
            counters['mode_total'] += 1
        elif event == HeartbeatThread.HBEvent.KICK:
            counters['kick'] += 1
            counters['kick_total'] += 1
        elif event == HeartbeatThread.HBEvent.CHAN_MSG:
            counters['chan_msg'] += 1
            counters['chan_msg_total'] += 1
        else:
            assert None, 'Unreachable'

    def _shutdown(self):
        self._log.info('HeartbeatThread going away')

    def _should_log_heartbeat(self):
        now = time.time()
        interval = self._interval
        if interval < 0:
            return False
        last = self._last
        return last + interval < now

    def _log_heartbeat(self):
        log = self._log
        counters = self._counters
        self._last = time.time()
        runtime = seconds_to_duration(self._last - self._start)
        log('Running for {runtime}. '
            '{cmsg} chan msgs ({cmsg_t} since start); '
            '{nadd} added nicks ({nadd_t}); '
            '{nchange} changed nicks ({nchange_t}); '
            '{ndel} removed nicks ({ndel_t}); '
            '{mode} mode changes ({mode_t}); '
            '{kick} kicks ({kick_t}); '
            '{qadd} added quiets ({qadd_t}); '
            '{qdel} deleted quiets ({qdel_t}); '
            '{bdel} deleted akicks ({bdel_t}).'
            .format(
                runtime=runtime,
                nadd=counters['add_nick'], nadd_t=counters['add_nick_total'],
                nchange=counters['change_nick'],
                nchange_t=counters['change_nick_total'],
                ndel=counters['del_nick'], ndel_t=counters['del_nick_total'],
                qadd=counters['quiet_add'], qadd_t=counters['quiet_add_total'],
                badd=counters['akick_add'], badd_t=counters['akick_add_total'],
                qdel=counters['quiet_del'], qdel_t=counters['quiet_del_total'],
                bdel=counters['akick_del'], bdel_t=counters['akick_del_total'],
                mode=counters['mode'], mode_t=counters['mode_total'],
                kick=counters['kick'], kick_t=counters['kick_total'],
                cmsg=counters['chan_msg'], cmsg_t=counters['chan_msg_total']
            ))
        counters['add_nick'] = 0
        counters['change_nick'] = 0
        counters['del_nick'] = 0
        counters['quiet_add'] = 0
        counters['quiet_del'] = 0
        counters['akick_add'] = 0
        counters['akick_del'] = 0
        counters['mode'] = 0
        counters['kick'] = 0
        counters['chan_msg'] = 0

    def update_global_state(self, gs):
        self._log = gs['log']
        conf = gs['conf']
        self._interval = 60 * 60 * 4  # 4 hours
        if 'log' in conf and 'heartbeat_interval' in conf['log']:
            self._interval = conf.getint('log', 'heartbeat_interval')
        if self._interval == 0:
            self._log('HeartbeatThread defaulting to 4hr interval')
            self._interval = 60 * 60 * 4  # 4 hours
        elif self._interval < 0:
            self._log('HeartbeatThread disabled with negative interval')
        self._last = time.time()
        self._is_shutting_down = gs['events']['is_shutting_down']

    def _add(self, event):
        ''' Called (indirectly) from other threads '''
        assert isinstance(event, HeartbeatThread.HBEvent)
        self._event_queue.put(event)

    def event_add_nick(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.ADD_NICK)

    def event_del_nick(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.DEL_NICK)

    def event_change_nick(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.CHANGE_NICK)

    def event_add_quiet(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.QUIET_ADD)

    def event_del_quiet(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.QUIET_DEL)

    def event_del_akick(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.AKICK_DEL)

    def event_set_mode(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.SET_MODE)

    def event_kick(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.KICK)

    def event_chan_msg(self):
        ''' Call from other threads when events happen '''
        return self._add(HeartbeatThread.HBEvent.CHAN_MSG)
