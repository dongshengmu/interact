#!/usr/bin/env python
# Class InteractiveSubprocess, a subprocess to interactively execute command and capture output.
# Copyright (c) 2014 Dongsheng Mu.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)


from curses import ascii
import errno
import os
import pty
import re
import select
import shlex
import sys
import subprocess
import time
import types
import util


#
# subprocess, to interact with shell, process.
#
class InteractiveSubprocess(object):
    """Module for an interactive subprocess class.

    A programmably interactive process, useful to control
    a command line interface driven device or process, such like gdb.
    """

    # class constants
    FOREVER = 'forever'
    NO_WAIT = 'no_wait'
    # special ASCII keys
    CTRL_A = '\x01'
    CTRL_C = '\x03'
    CTRL_D = '\x04'
    CTRL_SQUARE = '\x1d'

    def __init__(self, cmd, name='', prompt=None, timeout=5, delay=0.1, idleout=None,
                 use_pty_stdin=False, use_pty_stdout=False, use_shell=False,
                 print_input=lambda x: util.print_cyan(x, end=''),
                 print_output=util.print_no_newline,
                 print_stderr=lambda x: sys.stderr.write(util.colored(x, ['magenta'])),
                 print_warn=util.print_warn,
                 print_error=util.print_error,
                 hide_output=False,
                 flush=False, scrollback=False,
                 retry=0, lazy=False,
                 disable_echo=False,
                 auto_reconnect=False):
        """Open a programmably interactive process.

        Parameters:

        - cmd: the command line to start the process.
        - name: a string name for the process.
        - prompt: the command prompt of the process. If specified, when the prompt is
                found in the program output, a command execution is considered done.
                This prompt string can be regex pattern.
        - timeout: value in seconds, to timeout a command execution, in case
                the prompt or expected output is not found. If None, default to 5.
        - delay: value in second (can be 0.00x), max time to wait in select().
        - idleout: value in seconds, return if no more output for certain time.
                If idleout is None, won't check the output idle time.
        - use_pty_stdin: By default, stdin uses TTY native terminal device.
                Set this flag to True, to avoid tcgetattr error, for programs
                which use PTY pseudo terminal device as stdin.
        - print_intput: method to print the input command send to the process.
        - print_output: method to print the process's stdout output.
        - print_stderr: method to print the process's stderr output.
        - print_warn: method to print any warning and non-critical error.
        - print_error: method to print any critical error.
        - hide_output: if True, don't print the output of process starting.
        - flush: If true, flush the program's startup output.
        - scrollback: If true, archieve all the output in scrollback_buf, for later use.
        - retry: number of times to retry to connect in case initial connection fails.
        - lazy: If False, spawn the subprocess immediately. If True, defer the actual spawn,
                which can be done later when the subprocess is actually used.
        - disable_echo: if True, disable the terminal echo for input characters,
                so the output log can be cleaner for some application.
        - auto_reconnect: if True, attemp to reconnect if a connection is dropped

        NOTE: it uses fcntl to have a non-blocking pipe file object for
        subprocess, so that stdout.read won't hang. This only works for UNIX.
        """

        # init default values
        self.cmdline = cmd
        self.name = name
        self.prompt = prompt
        self.delay = delay
        self.timeout = timeout if timeout is not None else 5
        self.idleout = idleout
        self.max_idle_gap = 0   # record the max idle gap between outputs within 1 execution.
        self._idle_gaps = [0]
        self.use_pty_stdin = use_pty_stdin
        self.use_pty_stdout = use_pty_stdout
        self.use_shell = use_shell
        self._init_retry = retry
        self._init_flush = flush
        self.hide_output = hide_output
        self._remaining_output = ''      # remaining stdout output from previous execution
        self._remaining_err_output = ''  # remaining stderr output from previous execution
        self._peek_out = self._peek_err = ''  # store any peeked output for later use.
        no_print = lambda x: None
        self.print_input = print_input if print_input else no_print
        self.print_output = print_output if print_output else no_print
        self.print_stderr = print_stderr if print_stderr else no_print
        self.print_warn = print_warn if print_warn else no_print
        self.print_error = print_error if print_error else no_print
        self.scrollback = scrollback
        self.scroll_buf = ''
        self._disable_echo = disable_echo
        self._replace_ctrl_c = False
        self._auto_reconnect = auto_reconnect
        self._had_connect = False

        if not lazy:
            self._connect()

    def __getitem__(self, item):
        return getattr(self, item)

    def _connect(self):
        """spawn the interactive subprocess."""
        if not (hasattr(self, 'cmdline') and self.cmdline):
            # No cmd to run, return a class instance without subprocess process.
            return None

        # open the process, as a subprocess.Popen object.
        self.print_input('Starting interactive-process %s: %s\n' % (self.name, self.cmdline))
        cmd_list = self.cmdline if self.use_shell else shlex.split(self.cmdline)

        for attempt in xrange(self._init_retry + 1):
            if self.use_pty_stdin or self.use_pty_stdout:
                # Use a PTY pseudo terminal, for program that does tcgetattr, or other cases.
                # with util.SudoPrivilege():   #FIXME: openpty may get 'Out of devices' error w/o sudo
                master, slave = pty.openpty()
            p = subprocess.Popen(cmd_list, bufsize=0,
                                 stdin=slave if self.use_pty_stdin else subprocess.PIPE,
                                 stdout=slave if self.use_pty_stdout else subprocess.PIPE,
                                 stderr=subprocess.PIPE, shell=self.use_shell,
                                 universal_newlines=True)
            self.stdin = os.fdopen(master, 'w', 0) if self.use_pty_stdin else p.stdin
            self.stdout = os.fdopen(master, 'rU', 0) if self.use_pty_stdout else p.stdout
            self.stderr = p.stderr
            if not p:
                self.print_warn('fail to open %s process, "%s".' % (self.name, self.cmdline))

            # change the pipe to non-blocking
            util.tty_nonblocking(self.stdout)
            util.tty_nonblocking(self.stderr)
            # disable echo for cleaner output
            if self._disable_echo:
                util.term_set_echo(self.stdin.fileno(), enable=False)

            self.process = p

            self.peek()
            if self.is_alive():
                # connected
                break
            util.print_progress('Will retry "%s" in 1 sec, %s attempt ...' %
                                (self.cmdline, attempt + 1), color=['cyan'])
            time.sleep(1)

        self.print_input('\n')
        if not self.is_alive():
            self.print_error('fail to connect to %s, "%s", with %d retries.'
                             % (self.name, self.cmdline, self._init_retry))
            return None

        if self._init_flush:
            # set continuous_output to reuse previous flushed output
            self.flush(expect='', hide_output=self.hide_output, continuous_output=True)

        self._had_connect = True
        return self.process

    def _reconnect(self):
        """Reconnect if connected before and now the connection is dropped.
        Useful to start from fresh after a failed loop of test.
        """
        if self._had_connect and not self.is_alive():
            self._connect()

    def __call__(self, *args, **kwargs):
        """Default classname() to classname.cmd(), without return."""
        if not self.is_alive():
            if self._auto_reconnect:
                self.print_warn('Connection %s dropped, reconnecting' % self.name)
                self._connect()
            else:
                self.print_error('Connection %s dropped' % self.name)
                return
        return self.cmd(*args, **kwargs)

    @util.return_o_e
    def console(self, cmd='', expect=None, show_cmdbuf=True, rtn_cmdbuf=False):
        """Attach main program's console to the subprocess's console for its input and output.
        This allows user to manually interact with the subprocess. The subprocess console will be
        detached either by Ctrl-], or when the expect regex is found.

        - cmd: an optional command to be executed, default is an Enter key to display console prompt.
        - expect: a regex to expect, if found, detached from the subprocess and return (o, e).
        - show_cmdbuf: if True, and if exited with Ctrl-], print the manual steps done within the console session.
                Note, special keys (arrow, tab, delete, etc) are printed as raw.
        - rtn_cmdbuf: if True, return the intercepted user input as a string, together with (o, e)
        - return: return (o, e), the outputs from stdout and stderr,
                When exit with Ctrl-], return (o, e, cmdbuf) if rtn_cmdbuf is True, else None.
        """

        if not self.is_alive():
            self.print_warn('Connection %s dropped, reconnecting' % self.name)
            self._connect()
        util.print_header("Console attached to '%s'. Escape character is '^]'" % self.name)

        if cmd is not None:
            cmd = cmd.strip() + '\n'

        results = self.cmd_interact(cmd=cmd, expect=expect, timeout=self.FOREVER)

        if len(results) == 3:
            o, e, steps = results
            steps = steps.splitlines()
            util.print_header('Console detached from "%s", by Ctrl-]' % self.name)
            if show_cmdbuf:
                util.print_green("Here are the manual steps done in interactive console of %s:" % self.name)
                for x in steps:
                    util.print_green('    %s' % x.__repr__())
                print('')
            if rtn_cmdbuf:
                return o, e, steps
            return  # return None to keep interactive console clean.
        else:
            o, e = results
            util.print_header('Console detached from "%s"' % self.name)
            return o, e

    def is_alive(self, warn=False):
        """Return True if the subprocess is alive."""
        if self.process is None:
            return False
        stat = self.process.poll()
        if stat is not None and warn:
            self.print_warn('Process %s has exited with code %s' % (self.name, stat))
        return stat is None

    def change_timeout(self, timeout):
        self.timeout = timeout

    def change_prompt(self, prompt):
        self.prompt = prompt

    def _measure_idle(self, idle_start):
        old_start = idle_start
        idle_start = time.time()
        if old_start:
            self._idle_gaps.append(idle_start - old_start)
        return idle_start

    @util.return_o_e
    def send(self, inputkeys, expect='', delay=None, timeout=None, idleout=None,
             new_prompt=None, hide_input=False, hide_output=False,
             continuous_output=False, ignore_no_output=False, end_with_newline=False,
             peek=False, intercept_stdin=None):
        """Execute a cmd in the process, or send some input to the process.

        - inputkeys: key stokes to send to the process. Need to include '\\n' for
                command.
        - expect: a string is expected from the process output. Return when it
                is found.
                If it is '' (default), the execution returns when the
                process prompt is found.
                If it is None, no expected output, return on timeout instead.
        - new_prompt: If not None, change the default prompt. Some command execution will affect the default prompt,
                such like changing shell or changing the working dir in a server connection.
        - delay: delay certain time (in second, can be 0.x) before check any output.
        - timeout: timeout value (in second) for the command execution.
                If it is None, the default timeout of the process is used.
                If it is FOREVER, unlimited timeout, wait for expected output forever, or till idleout.
                If it is NO_WAIT, return immediately without waiting for any output. This is not a recommended usage.
        - idleout: value in seconds, return from if the output has been idle for certain time.
        - hide_input: if True, don't print the input, eg. for sending password.
        - hide_output: if True, don't print the process output for this call.
        - continuous_output: If True, merge any previously leftover output with the new output,
                useful for periodical polling.
                Default is False, as each command execution has its own discrecte output,
                any previous leftover is neither used in pattern search nor returned as current output.
        - peek: Check the output, but leave the output data for later consumption
        - intercept_stdin: a input terminal fd be intercepted and piped to the
                subprocess. This allows user to response to a program that prompt for user input
                (such like 'svn update' abnorm case handling).
        - return: a tuple of (o, e), the process's stdout and stderr outputs.
        """

        if not self.is_alive():
            err = 'Connection "%s" not alive.' % self.name
            util.print_error(err)
            return '', 'ERROR: ' + err
        p = self.process
        if timeout is None:
            timeout = self.timeout
        if idleout is None:
            idleout = self.idleout
        delay = delay if delay else self.delay
        delay = min(timeout, delay)
        if new_prompt:
            self.change_prompt(new_prompt)
        if expect == '':
            expect = self.prompt
        print_output = (lambda x: None) if hide_output else self.print_output
        print_stderr = (lambda x: None) if hide_output else self.print_stderr

        start_time = time.time()
        idle_start = None
        # flush out any previous leftover output in the stdout/stderr internal buffer
        if p.poll() is None:
            has_oe = select.select([self.stdout, self.stderr], [], [], 0)[0]
            if self.stdout in has_oe:
                self._remaining_output += self.stdout.read()
                if not continuous_output:
                    print_output('previous remaining stdout output: "%s"' %
                                 self._remaining_output)
                else:
                    print_output(self._remaining_output)
                if continuous_output and idleout:
                    idle_start = time.time()
            if self.stderr in has_oe:
                self._remaining_err_output += self.stderr.read()
                if not continuous_output:
                    print_stderr('previous remaining stderr output: "%s"' %
                                 self._remaining_err_output)
                else:
                    print_stderr(self._remaining_err_output)
                if continuous_output and idleout:
                    idle_start = time.time()

        # send input to process
        if inputkeys:
            if not hide_input:
                self.print_input(inputkeys)
            self.stdin.write(inputkeys)
            self.stdin.flush()
        intercept_buf = ''

        if timeout == self.NO_WAIT:
            # return without wait for any output. This is not a common use case.
            self.print_warn('timeout==NO_WAIT, returned without waiting for any output. '
                            'The output from "%s" may defer to next execution.' % inputkeys.__repr__())
            return '', ''

        # now wait for the output.
        output = self._peek_out
        self._peek_out = ''
        previous_output = ''
        if self._remaining_output:
            if continuous_output:
                output += self._remaining_output
            else:
                previous_output = self._remaining_output
            self._remaining_output = ''

        err_output = self._peek_err
        self._peek_err = ''
        previous_err_output = ''
        if self._remaining_err_output:
            if continuous_output:
                err_output += self._remaining_err_output
            else:
                previous_err_output = self._remaining_err_output
            self._remaining_err_output = ''

        if p.poll() is not None:
            # program exited
            has_oe = select.select([self.stdout, self.stderr], [], [], 0)[0]
            if self.stdout in has_oe:
                o = self.stdout.read()
                output += o
                print_output(o)
            if self.stderr in has_oe:
                eo = self.stderr.read()
                err_output += eo
                print_stderr(eo)
            if not hide_output:
                self.print_warn('Process %s has exited with code %s' % (self.name, p.poll()))

        select_terminals = [self.stdout, self.stderr]
        if intercept_stdin:
            select_terminals.append(intercept_stdin)
        while p.poll() is None:  # check whether the process exits.
            # wait on terminal IO
            try:
                has_ioe = select.select(select_terminals, [], [], delay)[0]
            except select.error as (code, msg):
                if code == errno.EINTR:
                    # with error: (4, 'Interrupted system call'). This EINTR exception is normal
                    self.print_warn('Ignored: %s, %s' % (code, msg))
                    has_ioe = []
                else:
                    self.print_error('Error: %s, %s' % (code, msg))
                    raise

            if intercept_stdin and intercept_stdin in has_ioe:
                i = intercept_stdin.read()
                if i == self.CTRL_C:
                    if self._replace_ctrl_c:
                        self.ctrl_c()
                        intercept_buf += i
                        continue
                if i == self.CTRL_SQUARE:
                    # Ctrl-] escape key pressed
                    return output, err_output, intercept_buf
                intercept_buf += i
                self.stdin.write(i)
                self.stdin.flush()
                if self._disable_echo:
                    # FIXME, once turn back on ECHO for console(),
                    # could not get the echo to treat '\r' as CRLF,
                    # thus doing software echo for now.
                    if ascii.isprint(i):
                        self.print_input(i)
                    elif i == '\r':
                        self.print_input('\n')
            if self.stderr in has_ioe:
                # now, check the stderr output
                try:
                    eo = self.stderr.read()
                    print_stderr(eo)
                    err_output += eo
                    if idleout:
                        idle_start = self._measure_idle(idle_start)
                except IOError:
                    pass
            if self.stdout in has_ioe:
                try:
                    o = self.stdout.read()
                    print_output(o)
                    output += o
                    if idleout:
                        idle_start = self._measure_idle(idle_start)
                except IOError:
                    pass

            if expect:
                # check stdout output
                m = re.search(expect, output)
                if m:
                    self._remaining_output = output[m.end():]
                    output = output[: m.end()]
                    break
                # check stderr err_output
                m = re.search(expect, err_output)
                if m:
                    self._remaining_err_output = err_output[m.end():]
                    err_output = err_output[: m.end()]
                    break
            if (timeout != self.FOREVER) and time.time() - start_time >= timeout:
                if (timeout != self.FOREVER) and expect:
                    self.print_warn('%s timed out for "%s", timeout %0.3f seconds, '
                                    'expect "%s".'
                                    % (self.name, inputkeys.__repr__(), timeout, expect))
                break
            if idleout and idle_start is not None:
                if time.time() - idle_start >= idleout:
                    if expect:
                        self.print_warn('%s idled out for "%s", idleout %0.3f seconds, '
                                        'past max_idle_gap %0.3f, this max_gap %0.3f, '
                                        'expect "%s".' %
                                        (self.name, inputkeys.__repr__(), idleout,
                                         self.max_idle_gap, max(self._idle_gaps[1:] + [0]),  # in case empty
                                         expect))
                    break
        # end while loop

        if idleout:
            self.max_idle_gap = max(self._idle_gaps)
            self._idle_gaps = [self.max_idle_gap]   # so it won't accumulate over time
        if expect and (not output) and (not ignore_no_output):
            self.print_warn('%s has no output for "%s", expecting "%s".'
                            % (self.name, inputkeys.__repr__(), expect))

        if peek:
            self._peek_out = output
            self._peek_err = err_output
        if self.scrollback:
            # previous leftover output is always stored in the scroll buff
            self.scroll_buf += previous_output + output
            self.scroll_buf += previous_err_output + err_output

        if (not output.endswith('\n')) and end_with_newline:
            # normal cmd prompt doesn't start a newline, it is hard to read when other print
            # appended to the end of this prompt line. Thus we start a newline for other prints.
            print_output('\n')

        return output, err_output

    def cmd(self, cmd=None, timeout=None, new_prompt=None, *args, **kwargs):
        """Execute a command.
        Compare to send(), cmd() will make sure the input ends with a single `\\n`
        to avoid multiple prompts, and make sure the cursor ends at the begining
        of a newline to avoid subsequent program print mixing with the command output.

        - cmd: command to be executed. A `\\n` is appended if the cmd is not terminated with `\\n`.
            If it is None, simply check the subprocess's output without sending any input.
        - timeout: timeout value (in second) for the command execution.
            If it is None, the default timeout of the process is used.
            If it is FOREVER, unlimited timeout, wait for expected output forever, or till idleout.
            If it is NO_WAIT, return immediately without waiting for any output. This is not common, suggest use 0.01s.
        - new_prompt: If not None, change the default prompt. Some command execution will affect
            the default prompt, such like changing shell or changing the working dir in a server connection.
        """
        if cmd is not None:
            cmd = cmd.strip() + '\n'
        return self.send(inputkeys=cmd, timeout=timeout, new_prompt=new_prompt,
                         end_with_newline=True, *args, **kwargs)

    def cmd_hide(self, cmd=None, hide_input=True, hide_output=True, *args, **kwargs):
        """Hide the input/output, but not errors. Useful for backend task of no user interest.

        NOTE: this method will be overridden as self.cmd() if verbose level >= SHOW_BACKEND.
              For critical info, such like password input, caller of cmd_hide should explictly
              speicify hide_input=True.
        """
        return self.cmd(cmd=cmd, hide_input=hide_input, hide_output=hide_output, *args, **kwargs)

    @util.return_o_e_r
    def cmd_search(self, cmd, pattern, reverse=False, sum_value=None, verbose=True, *args, **kwargs):
        """Execute a command and check whether a specified regex pattern is in the command output.

        - cmd: command to be executed.
        - pattern: a regex pattern, once it is found in the command output, polling is completed.
        - reverse: reverse the logic, once the pattern is not longer found, polling is completed.
        - sum_value: if specified, poll till the sum of multiple pattern instances matches the value.
          Note, using both reverse and sum_value is not supported.
        - verbose: if True, show output from all polling iterations. If False, only show output of last poll.
        - \*args, \*\*kwargs: optional parameters for self.cmd()

        - return: (output, stderr_output, result), outputs of the last execution, and whether found
          expected result.
        """
        o, e = (self.cmd if verbose else self.cmd_hide)(cmd, *args, **kwargs)
        m = re.search(pattern, o)
        if sum_value is not None:
            assert not reverse, 'Using both sum_value and reverse is not supported.'
            m = sum_value == util.get_sum(pattern, o)
        r = bool(m) != bool(reverse)
        return o, e, r

    @util.return_o_e_r
    def cmd_poll(self, cmd, pattern, reverse=False, sum_value=None, max_times=10, interval=0.1,
                 initial_delay=0, verbose=1, *args, **kwargs):
        """Execute a command multiple times until a specified pattern is in the command output.
        E.g. waiting for a prcoess completing some time consuming task by polling a command.

        - cmd: command to be executed.
        - pattern: a regex pattern, once it is found in the command output, polling is completed.
        - reverse: reverse the logic, once the pattern is not longer found, polling is completed.
        - sum_value: if specified, poll till the sum of multiple pattern instances matches the value.
          Note, using both reverse and sum_value is not supported.
        - max_times: specify the maximum times the command should be executed to wait for the pattern.
        - interval: time interval between command execution, specified in fraction number of seconds.
        - initial_delay: time to be delayed before starting the polling.
        - verbose: 0: no log, 1: show output of last poll, 2: show output from all polling iterations.
        - \*args, \*\*kwargs: optional parameters for self.cmd()

        - return: (output, stderr_output, result), outputs of the last execution, and whether the polling
          succeeds in getting expected result.
        """
        o = e = ''
        i = 0
        for i in xrange(max_times + 1):
            if not self.is_alive():
                self.print_error('\n%s not alive, cmd_poll "%s" returned, polled %d times' %
                                 (self.name, cmd, i))
                return o, e, None
            time.sleep(initial_delay if i == 0 else interval)
            o, e, r = self.cmd_search(cmd, pattern=pattern, reverse=reverse, sum_value=sum_value,
                                      verbose=(verbose == 2), *args, **kwargs)
            if r:
                break
            progress = ('cmd_poll: time spent %.2f seconds, (delay %s, interval %s, %s times), result %s ...' %
                        (i * interval + initial_delay, initial_delay, interval, i, r))
            if verbose == 2:
                self.print_input('%s\n' % progress)
            elif verbose == 1:
                util.print_progress(progress, color=['cyan'])
        else:
            # did not get the expected polling result
            r = False
        util.print_progress('')
        if verbose:
            self.print_input('%s cmd_poll "%s": waited %.2f seconds, result %s\n'
                             % (self.name, cmd, i * interval + initial_delay, r))
        if not r:
            self.print_error('%s cmd_poll failed %sto get "%s", waited %.2f seconds' %
                             (self.name, 'NOT ' if reverse else '', pattern, i * interval + initial_delay))
        if verbose == 1 or (verbose == 0 and not r):
            self.print_output('\n%s\n' % o)
            self.print_stderr('%s\n' % e)
        return o, e, r

    def cmd_batch(self, cmds, stop_on_error=False, hide_pass=False, precall=None, preargs=(), prekwargs=None,
                  postcall=None, postargs=(), postkwargs=None, return_pass_fail=False, *args, **kwargs):
        """Execute a list of commands, return a list of (cmd, stdout_output, stderr_output, result)

        - cmds: a list of command/dict, comment or (command/dict, pass_pattern) to be executed in the sequence order.
            For items of (command/dict, pass_pattern) the pass_pattern is matched in stdout_output
            and pass/fail is printed. The command can be a string command, or a dict of arguments
            for self.cmd() method, if it is a dict, the common args/kwargs won't be used.
            A string staring with '#' is a comment, and will be printed.

            Supported cmd format::

                '# comment' :
                    A comment to be printed.
                'cmd' :
                    Execute a cmd, with the common arguments specified in \*\*kwargs.
                dict(cmd='cmd', timeout=80, expect='xxx', ...) :
                    execute a cmd, with user specified arguments for the cmd.
                ('cmd' or dict, pass_pattern) :
                    Execute cmd or a dict cmd on, and
                    check the pass_pattern in command outputs.
                    - pass_pattern is a regex string, if found, the command is considered as passed.
                    - Command without pass_pattern specified is treated as pass.

        - stop_on_error: if a step fail, do not continue the rest steps.
        - hide_pass: do not print the pass message of pattern checking.
        - precall: python function to be called before each cmd, cmd execution will
            be skipped if precall returns False.

            - precall(cmd, results, \*preargs, \*\*prekwargs)
            - cmd: the next command to be executed.
            - results: a list of (cmd, o, e, r) of all preceeding steps.
            - eg: precall = lambda cmd, results: pause_for_a_key('press s to skip') != 's'
        - preargs: tuple arguments for precall
        - prekwargs: keyword arguments for precall
        - postcall: python function to be called after each cmd execution.
            - postcall(cmd, o, e, r, \*postargs, \*\*postargs)
            - cmd: the command had just executed
            - o, e: the stdout, stderr output from the command
            - r: the result whether the output has the regex pass_pattern.
                None if no pass_pattern specified for this command.
            - eg: postcall = lambda cmd, o, e, r: do_pass() if expected_result[cmd] in o else do_fail()
        - postargs: list of arguments for postcall
        - postkwargs: keyword arguments for postcall
        - return_pass_fail: if True, return False if any command execution does not have expected result.
        - return: a list of (cmd, o, e, r), or True/False if return_pass_fail is True.
        """
        if prekwargs is None:
            prekwargs = {}
        if postkwargs is None:
            postkwargs = {}
        results = []
        if isinstance(cmds, str):
            cmds = cmds.splitlines()
        for x in cmds:
            if isinstance(x, str) and x.startswith('#'):
                # this is a comment
                util.print_green(x)
                results.append((x, None, None, None))
                continue
            if isinstance(x, (list, tuple)):
                # this is a command with a pass_pattern
                cmd, pass_pattern = x
            else:
                cmd, pass_pattern = x, None
            if precall and not precall(cmd, results, *preargs, **prekwargs):
                results.append((cmd, None, None, None))
                continue
            # execute the command
            if isinstance(cmd, dict):
                # this is a dict, a command with its specfic arguments
                o, e = self.cmd(**cmd)
            else:
                # this is a command that uses the batch's common arguments
                o, e = self.cmd(cmd, *args, **kwargs)
            if pass_pattern:
                if re.search(pass_pattern, o):
                    r = True
                    if not hide_pass:
                        util.print_pass('pattern "%s" found in "%s" output' % (pass_pattern, cmd))
                else:
                    r = False
                    util.print_fail('pattern "%s" NOT found in "%s" output' % (pass_pattern, cmd))
            else:
                r = None
            results.append((cmd, o, e, r))
            if r is False and stop_on_error:
                return False if return_pass_fail else results
            if postcall:
                postcall(cmd, o, e, r, *postargs, **postkwargs)

        if return_pass_fail:
            results = [x for x in results if x[3] is False] == []
        return results

    def cmd_interact(self, cmd=None, *args, **kwargs):
        """Execute a command, and accept manaul interaction with user keyboard input."""
        if cmd is not None:
            cmd = cmd.strip() + '\n'
        # Use raw mode terminal, to pass control characters (arrow, ctrl-c, tab, etc) to program.
        ttyin = util.NonblockStdin().stdin
        with util.TerminalMode(ttyin, raw=True, nonblock=True):
            return self.send(inputkeys=cmd, intercept_stdin=ttyin, *args, **kwargs)

    def expect(self, expect='', timeout=None):
        """Check and wait for an expected output."""
        return self.send(inputkeys=None, expect=expect, timeout=timeout)

    def poll(self):
        """Return current output, without waiting."""
        return self.send(inputkeys=None, expect=None, timeout=0)

    def flush(self, expect='', timeout=None, idleout=None, hide_output=False, **kwargs):
        """Flush any previous output buffered.

        NOTE: Useful to flush the remaining output after a cmd was executed with an
            expect string, so the next cmd execution will only check its own output.

        This is same as calling send(inputkeys=None, expect, timeout, hide_output).
        The parameters are same as in send()
        """
        return self.send(inputkeys=None, expect=expect, timeout=timeout, idleout=idleout,
                         hide_output=hide_output, **kwargs)

    def check_outputs(self, expect=None, timeout=0, **kwargs):
        """Return any outputs a subprocess produced between last time check and now.
        Useful to get the output from a subprocess that is put to run in parallel.
        """
        return self.send(inputkeys=None, expect=expect, timeout=timeout, continuous_output=True, **kwargs)

    def peek(self, expect=None, timeout=0.1, idleout=None, hide_output=True, **kwargs):
        """Peek for any output, but leave the output for later consumption."""
        return self.send(inputkeys=None, expect=expect, timeout=timeout, idleout=idleout,
                         hide_output=hide_output, peek=True, **kwargs)

    def _send_special(self, key, key_name, expect='', **kwargs):
        """Send special ASCII code to the process."""
        self.print_input('Send %s to %s.\n' % (key_name, self.name))
        self.stdin.write(key)
        self.stdin.flush()
        return self.flush(expect=expect, end_with_newline=True, **kwargs)

    def ctrl_c(self, expect='', **kwargs):
        """Send a Ctrl-C SIGINT to the process."""
        return self._send_special(self.CTRL_C, 'Ctrl-C SIGINT', expect=expect, **kwargs)

    def ctrl_d(self, expect='', **kwargs):
        """Send a Ctrl-D End-Of-Transmission to the process."""
        return self._send_special(self.CTRL_D, 'Ctrl-D EOT', expect=expect, **kwargs)

    def ctrl_square(self, expect='', **kwargs):
        """Send a Ctrl-] to the process."""
        return self._send_special(self.CTRL_SQUARE, 'Ctrl-]', expect=expect, **kwargs)

    def clear_buf(self):
        self.scroll_buf = ''

    def close(self):
        """Terminate the process."""
        if not self.is_alive():
            return
        self.process.terminate()

    def register_method(self, method):
        """To register an add-on method for existing classs instance.

        - method: a funciton defined as foo(self, ...)
        - return: True if successfully regitered the add-on.
        """
        if method.__name__ in self.__dict__:
            self.print_error('Method %s is already exist in object %s.' % (method.__name__, self))
            return False
        self.__dict__[method.__name__] = types.MethodType(method, self)
        return True


class LazyInteractiveSubprocess(InteractiveSubprocess):
    """A InteractiveSubprocess class with the actual subprocess lazy evaluated.
    The self.process will be initialized once, by child class's _connect() method,
    when the self.process is first time used.
    """
    def __init__(self, *args, **kwargs):
        """Initialize the instance properties, but defer the actual spawn of subprocess."""
        super(LazyInteractiveSubprocess, self).__init__(lazy=True, *args, **kwargs)

    @util.LazyProperty
    def process(self):
        """Lazy evaluator of self.process, to avoid the expensive initialization of process
        at class instance init time, and only evaluated self.process when it is first time used.
        Child class should provice a self._connect() method to evaluate and return the value of process.
        """
        return self._connect()
