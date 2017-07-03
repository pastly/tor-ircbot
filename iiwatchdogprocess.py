import os
import subprocess
from pbprocess import PBProcess
from signalstuff import *

class IIWatchdogProcess(PBProcess):
    def __init__(self, global_state):
        PBProcess.__init__(self, self._enter)
        self.update_global_state(global_state)

    def _enter(self):
        log = self._log_proc
        conf = self._conf
        ii_bin = conf['ii']['path']
        nick = conf['ii']['nick']
        server = conf['ii']['server']
        port = conf['ii']['port']
        server_pass = conf['ii']['server_pass']
        ircdir = conf['ii']['ircdir']
        print(ii_bin, nick, server, port, server_pass, ircdir)
        while True:
            self._prepare_ircdir()
            log.notice('(Re)Starting ii process')
            set_signals(self._ss, *get_default_signals(self._ss))
            ii = subprocess.Popen(
                [ii_bin,'-i',ircdir,'-s',server,'-p',port,'-n',nick,'-k','PASS'],
                env={'PASS': server_pass},
            )
            pop_signals_from_stack(self._ss)
            while not self._is_shutting_down.wait(10):
                # if we aren't shutting down and we have a return code,
                # then we need to restart the process. First exit this loop
                if ii.poll() != None:
                    log.debug('ii process went away')
                    break
            # if we have a return code from the ii sub-sub process, we just
            # exited the above loop and should restart this loop and thus
            # restart the ii process.
            if ii.poll() != None:
                continue
            # if we get to here, then we are shutting down and should just throw
            # it all away.
            if self._is_shutting_down.wait(2):
                log.notice('Stopping ii process for good')
                ii.terminate()
                break

    def _prepare_ircdir(self):
        conf = self._conf
        server_dir = os.path.join(conf['ii']['ircdir'],conf['ii']['server'])
        channel_name = conf['ii']['channel']
        os.makedirs(os.path.join(server_dir,channel_name), exist_ok=True)

    def update_global_state(self, gs):
        self._log_proc = gs['procs']['log']
        self._ss = gs['signal_stack']
        self._conf = gs['conf']
        self._is_shutting_down = gs['events']['is_shutting_down']
        if self._log_proc: self._log_proc.info('IIWatchProcess updated state')
