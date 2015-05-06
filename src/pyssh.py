#!/usr/bin/env python
# Interactive connection to a remote server via SSH, or to a local server with interactive bash.
# Copyright (c) 2014 Dongsheng Mu.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)


import os
import re
import time

import interact
import util


#
# telnet connection to a regular server.
#
class TelnetSession(interact.LazyInteractiveSubprocess):
    """An interactive subprocess connection of Telnet."""

    def __init__(self, hostname, username='regress', password='MaRtInI', su_password='Embe1mpls',
                 ip=None, port=None, prompt=None, timeout=10, **kwargs):
        """Init a InteractiveSubprocess telnet connection to a regular server.

        - hostname: the hostname shows in the telnet prompt.
        - username, password: the telnet login credentials.
        - su_password: sudo password, if specified, login su.
        - ip: IP address of the RE management interface, if hostname is not able to resolve.
        - port: a port number to be used for telnet, if need a non-default telnet port to connect the RE.
        - prompt: a regex string of the expected prompt.
          Default is a best guess, '(\\x1b\[[;\d]+m)?~(\\x1b\[0?m)?> |\][#|\>|\$] '

        """
        self.name = hostname
        self.prog = 'telnet -l %s %s %s' % (username, ip if ip else hostname, port if port else '')
        self.edit_prompt = '\[edit\]\nregress@%s# ' % hostname
        self.username = username
        self.password = password
        self.su_password = su_password
        # best guess of user prompt is '~> ', ']# ', or ']$ ', with or without ANSI color codes
        self.prompt = prompt if prompt else '(\\x1b\[[;\d]+m)?~(\\x1b\[0?m)?> |\][#|\>|\$] |% '
        super(TelnetSession, self).__init__(cmd=self.prog, name=self.name, prompt=self.prompt,
                                            use_pty_stdin=False, timeout=timeout, flush=False, **kwargs)

    def _connect(self):
        """Telnet connect to vre."""
        super(TelnetSession, self)._connect()
        # Register a exit handler to close the subprocess,
        # in case user script exits abnormally.
        util.exit_handler(self.close)

        # login and su
        self.cmd_hide(None, expect='Password:')
        self.cmd_hide(self.password, hide_input=True)
        if self.su_password:
            self.cmd_hide('su', expect='Password')
            self.cmd_hide(self.su_password, hide_input=True)
        # clear the password for credential reason. It is no longer needed after login.
        del self.password
        return self.process

    def close(self):
        # user may started other shell in the ssh connection, exit till the subprocess is closed.
        for i in xrange(5):
            if self.is_alive():
                try:
                    self.cmd_hide('exit', expect='exit|logout', ignore_no_output=i < 1)
                except ValueError:  # I/O operation on closed file
                    pass
            if self.is_alive():
                time.sleep(0.1)
            else:
                return
        else:
            # The shell may in a state not accepting exit cmd.
            # Call InteractiveSubprocess.close(), which kills the process directly.
            super(TelnetSession, self).close()

    def background_proc(self, *args, **kwargs):
        """To return a context manager for "with" statement. It will start and close a background process."""
        return BackgroundProcess(self, *args, **kwargs)


class PerhostTelnetSession(TelnetSession):
    __metaclass__ = util.Singleton
    """Singleton telnet conncetion."""


#
# SSH connection to regular server.
#
class SshSession(interact.LazyInteractiveSubprocess):
    """A subprocess connection to a regular server for interactive command execution."""
    def __init__(self, host=None, user=None, timeout=10, sshpass=None, **kwargs):
        """Open a InteractiveSubprocess with default settings.

        - host: a network hostname, IP address, or localhost.
            - If host is specified, use a SSH connection.
            - If host is None, use a interactive bash session.
        - user: if None, ssh login as the current user
        """
        self.username = user if user else os.getlogin()
        self.host = host
        self._init_flush = True
        self._init_prompt = False
        if self.host is None:
            # prepare for local connection
            if not hasattr(self, 'use_pty_stdin'):
                self.use_pty_stdin = True
            if not hasattr(self, 'hostname'):
                self.hostname = os.popen('hostname -s').read().strip()
            if not hasattr(self, 'name'):
                self.name = 'bash@%s' % self.hostname
            if not hasattr(self, 'cmdline'):
                # Note, "bash" non-interactive mode doesn't output prompt,
                # "bash -i" interactive mode output the prompt, but it has
                # error "Suspended (tty output)" when python put it in background.
                #
                # One workaround is a while loop of command eval in bash non-interactive mode with
                # a generated prompt, but the 'read line' prevents native console with raw terminal.
                # bash_cmd =
                # 'while true; do echo -n "`whoami`@`hostname -s` `pwd`> "; read line; echo "$line"; eval "$line"; done'
                # self.cmdline = "bash -c '%s'" % bash_cmd
                # self.prompt = '%s@%s .+> ' % (self.whoami, self.hostname)
                #
                # Other alternative workarounds are "bash -c csh", and ssh localhost.
                # We use "bash -c csh" here for better native console and no network traffic.
                self.cmdline = "bash -c csh"
                self.shelltype = 'csh'
            if not hasattr(self, 'prompt'):
                self.whoami = os.popen('whoami').read().strip()
                self.prompt = ''
                self._init_prompt = True
                self._init_flush = False
        else:
            self.use_pty_stdin = True,  # SSH requires Pseudo-terminal
            # prepare for remote connection
            self.whoami = self.username
            if not hasattr(self, 'cmdline'):
                self.cmdline = 'ssh ' + ('%s@' % self.username) + self.host
                if sshpass:
                    self.cmdline = ('sshpass -p %s ' % sshpass) + self.cmdline
            if not hasattr(self, 'name'):
                self.name = self.host
            if not hasattr(self, 'prompt'):
                # best guess of user prompt is '~> ', ']# ', or ']:# ', with or without ANSI color codes
                self.prompt = '(\\x1b\[[;\d]+m)?~(\\x1b\[0?m)?> |\]# |\]\:# '
        super(SshSession, self).__init__(cmd=self.cmdline,
                                         name=self.name, prompt=self.prompt,
                                         timeout=60,       # 60 seconds timeout for manual login
                                         use_pty_stdin=self.use_pty_stdin,
                                         flush=self._init_flush,         # Flush the startup messages
                                         **kwargs)
        self.timeout = timeout

    def _connect(self):
        """Establish a interactive connection and return the connection process."""
        if self.host is None:
            process = self._connect_local()
        else:
            process = self._connect_remote()
        if process:
            # Register a exit handler to close the subprocess,
            # in case user script exits abnormally.
            util.exit_handler(self.close)
        return process

    def _connect_remote(self):
        """Make the ssh connection and return the process object."""
        old_timeout = self.timeout
        self.timeout = 60   # to allow manual login
        super(SshSession, self)._connect()
        self.timeout = old_timeout

        # SSH login
        # If user has setup SSH keygen with no passphrase, the connection will continue and get expected prompt.
        # In the case that login credentials are needed, user has 60 seconds timeout to manually enter them,
        # for the prompts such like "Enter passphrase ...", "user@host's password:".

        if not self.is_alive():
            self.print_warn('Failed to SSH connect to "%s".' % self.host)

        if self._init_prompt:
            # To simplify the application level scripting, use a consistent prompt string.
            o, e = self.send('ps -p $$\n', idleout=5)      # As prompt is unknown yet, use idleout to avoid long timeout
            try:
                self.shelltype = re.search('\w+sh', o).group()
            except AttributeError:
                self.shelltype = 'bash'
            # Get the hostname from the machine, as user may have provided a IP address.
            o, e = self.send('hostname -s\n', idleout=5)
            self.hostname = o.split()[2]
            self.set_shell_prompt()
            self.print_output('\n')
        return self.process

    def _connect_local(self):
        """Connect to an interactive bash session on a local server."""
        super(SshSession, self)._connect()
        if self._init_prompt:
            self.set_shell_prompt()
        return self.process

    def set_shell_prompt(self):
        """Set the shell prompt to default, "user@hostname cwd> "."""
        prompt = '%s@%s .+> ' % (self.whoami, self.hostname)
        if 'csh' in self.shelltype:
            # csh or tcsh
            self.cmd_hide('set prompt="%n@%m %~> "', new_prompt=prompt)
        else:
            # bash etc
            self.cmd_hide('export PS1="\u@\h \w> "', new_prompt=prompt)

    def close(self):
        # user may started other shell in the ssh connection, exit till the subprocess is closed.
        for i in xrange(5):
            if self.is_alive():
                try:
                    self.cmd_hide('exit', expect='exit|logout', ignore_no_output=i < 1)
                except ValueError:  # I/O operation on closed file
                    pass
            if self.is_alive():
                time.sleep(0.1)
            else:
                return
        else:
            # The shell may in a state not accepting exit cmd.
            # Call InteractiveSubprocess.close(), which kills the process directly.
            super(SshSession, self).close()

    def background_proc(self, *args, **kwargs):
        """To return a context manager for "with" statement. It will start and close a background process."""
        return BackgroundProcess(self, *args, **kwargs)


class BackgroundProcess(object):
    """A class to be used with Python "with" statement, to start a background process for the
    execution of the code enclosed by the "with" statement, and terminate the process after.

    - cmd: command line to start the background process.
    - ready_pattern: a regex pattern indicating the process is completely started and ready.
    - timeout: max time to wait for the ready_pattern.
    """
    def __init__(self, tentacle, cmd, ready_pattern='', timeout=0.1):
        self.tentacle = tentacle
        self.cmd = cmd.strip(' &')
        self.pid = None
        self.ready_pattern = ready_pattern
        self.timeout = timeout
        self.o = self.e = ''

    def __enter__(self):
        o, e = self.tentacle.cmd(self.cmd + ' &', expect=self.ready_pattern, timeout=self.timeout)
        self.pid = util.get_num('\[\d+\] +(\d+)', o)
        if self.pid is None:
            util.print_error('Fail to get process id for "%s"' % self.cmd)
        self.o += o
        self.e += e
        return self

    def __exit__(self, _type, value, traceback):
        # kill with SIGQUIT causing mis-order of prompt and remaining output, so do fg then ctrl-c.
        o, e = self.tentacle.cmd('fg %s' % self.cmd, continuous_output=True,
                                 expect='\n%s\n|%s' % (self.cmd, self.tentacle.prompt))
        self.o += ''.join(x for x in o.splitlines(True)
                          if not x.endswith(self.cmd + '\n') and 'ambiguous job spec' not in x)
        self.e += e
        if 'ambiguous job spec' in o:
            # fg doesn't take pid, the string "job spec" sometimes can conflict with other process.
            # Retry with "fg" push stack.
            o, e = self.tentacle.cmd('fg', continuous_output=True, expect='\n' + self.cmd)
            self.o += ''.join(x for x in o.splitlines(True) if not x.endswith(self.cmd + '\n') and x != 'fg\n')
            self.e += e
        o, e = self.tentacle.ctrl_c(continuous_output=True)
        self.o += o
        self.e += e


#
# Singleton conncetions to local server.
#
class LocalSession(SshSession):
    __metaclass__ = util.Singleton


class PerhostSshSession(SshSession):
    __metaclass__ = util.SingletonPerParam
