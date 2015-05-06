#!/usr/bin/env python
# Misc little utilities.
# Copyright (c) 2014 Dongsheng Mu.
# License: MIT (http://www.opensource.org/licenses/mit-license.php)


from __future__ import print_function  # to use Python3 print function.

import atexit
import code
import fcntl
import fnmatch
import multiprocessing
import os
import re
import readline
import select
import stat
import sys
import termios
import time
import tty

from collections import namedtuple
from functools import wraps


#
# Colored print
#
def colored(text, colors):
    """Format text with ANSI color code, eg. '\033[31;44;1m' + text + '\033[0m'

    - colors: a list of color keywords from::

        Foreground color keywords:
            black, red, green, yellow, blue, magenta, cyan, white.
        Background color keywords:
            on_black, on_red, on_green, on_yellow, on_blue, on_magenta, on_cyan, on_white.
        Attributes:
            bold, dark, underline, blink, reverse, concealed.
    """
    ansi_color = {
        # foreground color codes
        'black':      30,
        'red':        31,
        'green':      32,
        'yellow':     33,
        'blue':       34,
        'magenta':    35,
        'cyan':       36,
        'white':      37,
        # background color codes
        'on_black':   40,
        'on_red':     41,
        'on_green':   42,
        'on_yellow':  43,
        'on_blue':    44,
        'on_magenta': 45,
        'on_cyan':    46,
        'on_white':   47,
        # attributes:
        'bold':        1,
        'dark':        2,
        'underline':   4,
        'blink':       5,
        'reverse':     7,
        'concealed':   8
    }

    if isinstance(colors, str):
        colors = [colors]
    color_code = ';'.join([str(ansi_color[x]) for x in colors if x in ansi_color])
    if color_code:
        return '\033[%sm%s\033[0m' % (color_code, text)
    else:
        return text


def no_color(text):
    """Remove ANSI color code, so to have a plain text."""
    color_regex = re.compile(r'\033\[(?P<arg_1>\d+)(;(?P<arg_2>\d+)(;(?P<arg_3>\d+))?)?m')
    return color_regex.sub('', text)


def print_green(s, **kwargs):
    print(colored(s, ['green']), **kwargs)


def print_red(s, end='\n'):
    print(colored(s, ['red']), end=end)


def print_yellow(s, end='\n'):
    print(colored(s, ['yellow']), end=end)


def print_magenta(s, end='\n'):
    print(colored(s, ['magenta']), end=end)


def print_blue(s, end='\n'):
    print(colored(s, ['blue']), end=end)


def print_cyan(s, end='\n'):
    print(colored(s, ['cyan']), end=end)


def print_no_newline(s):
    print(s, end='')


def print_normal(s, end='\n'):
    print(s, end=end)


def print_header(msg):
    start_newline()
    print('\n'.join(map(lambda x: colored(x, ['white', 'on_blue']), ('=== ' + msg).splitlines())))


def print_pass_banner(msg):
    print(colored('=== PASSED === ' + msg, ['white', 'on_green', 'bold']))


def print_fail_banner(msg):
    print(colored('=== FAILED === ' + msg, ['white', 'on_red', 'bold']))


def print_skip_banner(msg):
    print(colored('=== SKIPPED === ' + msg, ['red', 'on_yellow', 'bold']))


def print_pass(msg):
    start_newline()
    print_green('PASS: %s' % msg)


def print_fail(msg):
    start_newline()
    print_red('FAIL: %s' % msg)


def print_error(msg):
    start_newline()
    # make sure the 'ERROR:' tag is at same line of the msg.
    if msg.startswith('\n'):
        print('\n')
    print_color('ERROR:', ['black', 'on_red'], end=' ')
    print_red(msg.lstrip())


def print_warn(msg):
    start_newline()
    print_color('WARN:', ['red', 'on_yellow'], end=' ')
    print_red(msg)


def no_print(msg):
    return


def force_print(msg, color_code='green', end='\n'):
    """Unconditionally print, regardless of verbose setting."""
    start_newline()
    if color_code:
        msg = colored(msg, color_code)
    if isinstance(sys.stdout, OutputCapturor):
        # the sys.stdout is taken by OutputCapturor, use its unconditional print
        sys.stdout.print_no_hide(msg + end)
    else:
        print(msg, end=end)


def print_color(s, color_code, end='\n'):
    print(colored(s, color_code), end=end)


def terminal_width():
    """Return terminal window width."""
    width = 0
    try:
        import struct
        import fcntl
        import termios
        s = struct.pack('HHHH', 0, 0, 0, 0)
        x = fcntl.ioctl(1, termios.TIOCGWINSZ, s)
        width = struct.unpack('HHHH', x)[1]
    except IOError as e:
        print_warn(e)
    if width <= 0:
        width = 80

    return width


in_progress_print = False


def print_progress(msg, width=None, color='green'):
    """Print a progress msg in specified color, without starting a newline.
    Printing a empty msg will erase the previous progress msg.
    """
    if not width:
        width = terminal_width()
    sys.stderr.flush()  # flush any buffered stderr output to avoid mixed print.
    print_color('\r' + ' '*width + '\r' + msg[0: width - 1], end='', color_code=color)
    sys.stdout.flush()  # flush, to immediately show the progress without buffer delay.
    global in_progress_print
    in_progress_print = msg != ''


def start_newline():
    global in_progress_print
    if in_progress_print:
        print_progress('')
    elif isinstance(sys.stdout, OutputCapturor):
        if (sys.stdout.buf and (sys.stdout.buf[-1] != '\n')) or (not sys.stdout.at_newline):
            print('\n')


#
# Common regex operation
#
def get_multi_fields(pattern, o):
    """Extract multiple regex fields from a string."""
    if isinstance(pattern, str):
        pattern = re.compile(pattern)
    m = pattern.search(o)
    if m:
        return m.groups()
    else:
        return None


def get_field(pattern, o):
    """Extract a single regex field from a string."""
    m = get_multi_fields(pattern, o)
    if m:
        return m[0]
    else:
        return None


def get_num(pattern, o):
    """Extract a single regex field from a string, and convert it to integar."""
    field = get_field(pattern, o)
    return None if field is None else int(field)


def get_all_fields(pattern, o):
    """Extract the repeating instances that match a same single regex pattern."""
    if isinstance(pattern, str):
        pattern = re.compile(pattern)
    return pattern.findall(o)


def get_all_num(pattern, o):
    """Extract the repeating instances of a single regex num value pattern,
    and return a list of their integar values.
    Eg. get_sum('Rx +(\d+)', 'CPU1 Rx 10  Tx 34\\nCPU2 Rx 20  Tx 9') returns [10, 20].
    """
    return map(int, get_all_fields(pattern, o))


def get_sum(pattern, o):
    """Extract all fields of the single regex num value pattern,
    and return the sum of their integar values.
    Eg. get_sum('Rx +(\d+)', 'CPU1 Rx 10  Tx 34\\nCPU2 Rx 20  Tx 9') returns 30.
    """
    return sum(get_all_num(pattern, o))

#
# Misc
#
def full_ipv6(ip6):
    """Convert an abbreviated ipv6 address into full address."""
    return ip6.replace('::', '0'.join([':'] * (9 - ip6.count(':'))))


#
# Terminal related utilities
#
def peekch():
    """Check and return any key pressed, non-blocking."""
    ch = None
    if select.select([sys.stdin], [], [], 0)[0]:
        try:
            ch = sys.stdin.read(1)
        except IOError:     # [Errno 11] Resource temporarily unavailable
            pass
        except KeyboardInterrupt:
            ch == '\x03'    # Ctrl-C pressed
    return ch


def getch():
    """Wait for keypress and return the character."""
    # Set raw mode to skip line buffer. Set blocking mode so to wait for user.
    with TerminalMode(sys.stdin, raw=True, nonblock=False):
        ch = sys.stdin.read(1)
    return ch


def tty_nonblocking(fd):
    """set non-blocking attribute to a terminal fd."""
    old_fl = fcntl.fcntl(fd.fileno(), fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, old_fl | os.O_NONBLOCK)
    return old_fl


def pause_for_a_key(msg='Press any key to continue', check_quit=False):
    print_progress(msg + (', or q to quit' if check_quit else '...'))
    c = getch()
    print_progress('')
    if check_quit and c == 'q':
        exit()
    return c


def term_set_echo(fd, enable=True, when=termios.TCSAFLUSH):
    """To enable/disable terminal echo of input characters."""
    mode = termios.tcgetattr(fd)
    if enable:
        mode[tty.LFLAG] = mode[tty.LFLAG] | termios.ECHO
        # FIXME, disable works, but re-enable doesn't work well, try to get a result that printable
        # and CRLF get echoed, but the tab/arrow and other control doesn't echo and pass through to program.
        #mode[tty.LFLAG] = mode[tty.LFLAG] & ~(termios.ECHOCTL | termios.ECHOK | termios.ECHOE)
        #mode[tty.LFLAG] = mode[tty.LFLAG] | (termios.ECHO | termios.ECHONL | termios.ECHOPRT)
    else:
        mode[tty.LFLAG] = mode[tty.LFLAG] & ~termios.ECHO
        #mode[tty.LFLAG] = mode[tty.LFLAG] & ~(termios.ECHO | termios.ECHONL)
    termios.tcsetattr(fd, when, mode)


def term_enable_opost(fd, when=termios.TCSAFLUSH):
    """The tty.setraw() disables c_oflag.OPOST, the implementation-defined output processing.
    This causes UNIX terminal displaying LF without CR. This function enables OPOST.
    """
    mode = termios.tcgetattr(fd)
    mode[tty.OFLAG] = mode[tty.OFLAG] | termios.OPOST
    termios.tcsetattr(fd, when, mode)


class TerminalMode(object):
    """A class to be used by `with` statement, to temporarily use a specified terminal mode.
    The raw mode passes all keystrokes including control characters to the program.
    The cbreak mode disables line buffering and erase/kill character-processing, but
    intercept Ctrl-C.
    """
    def __init__(self, fd, raw=True, nonblock=True):
        if fd is None:
            self.fd = None
            return
        self.fd = fd.fileno()
        self.raw = raw
        self.nonblock = nonblock
        self.old_fl = fcntl.fcntl(self.fd, fcntl.F_GETFL)
        self.old_settings = termios.tcgetattr(self.fd)

    def __enter__(self):
        if self.fd is None:
            return
        if self.nonblock:
            fcntl.fcntl(self.fd, fcntl.F_SETFL, self.old_fl | os.O_NONBLOCK)
        else:
            fcntl.fcntl(self.fd, fcntl.F_SETFL, self.old_fl & ~os.O_NONBLOCK)
        if self.raw:
            tty.setraw(self.fd)
            term_enable_opost(self.fd)
        else:
            tty.setcbreak(self.fd)

    def __exit__(self, _type, value, traceback):
        if self.fd is None:
            return
        fcntl.fcntl(self.fd, fcntl.F_SETFL, self.old_fl)
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


class OutputCapturor(object):
    """A class to capture system stdout or stderr into string buffer."""
    def __init__(self, fileno, mirror=None, hide=False, swap=True):
        """Init a capturor object.

        - fileno: fileno of either sys.stdout or sys.stderr.
        - mirror: a mirror capturor, to which the output of this capturor is also writed.
            Useful to mirror the stderr output to stdout buf, so the time order of the 2 output is kept.
        - hide: if True, only save the output in string buffer, don't print.
        - swap: start capture the system output immediately when init this object.
        """
        self.buf = []
        self.hide = hide
        self.out = None
        assert fileno in [1, 2]     # only support sys.stdout and sys.stderr
        self.is_stdout = fileno == 1
        self.mirror = mirror
        self.at_newline = True
        self.in_progress_print = False
        if swap:
            self.swap_sys_output()

    def swap_sys_output(self):
        if self.out is None:
            self.out = sys.stdout if self.is_stdout else sys.stderr
            if self.is_stdout:
                sys.stdout = self
            else:
                sys.stderr = self

    def restore_sys_output(self):
        if self.out:
            if self.is_stdout:
                sys.stdout = self.out
            else:
                sys.stderr = self.out
            self.out = None

    def _buf(self, o):
        self.buf.append(o)
        if self.mirror is not None:
            self.mirror.buf.append(o)

    def _write(self, o):
        if self.out:
            self.out.write(o)
            self.out.flush()
            if o:
                self.at_newline = o[-1] == '\n'

    def write(self, o):
        self._buf(o)
        if not self.hide:
            self._write(o)

    def flush(self):
        if self.out:
            self.out.flush()

    def print_no_hide(self, o):
        """Print regardless of self.hide"""
        self._buf(o)
        self._write(o)

    def fileno(self):
        return 1 if self.is_stdout else 2

    def get_buf(self):
        return ''.join(self.buf)

    def clear_buf(self):
        self.buf = []


class Muter():
    """A class to be used by "with" statement, to temporarily hide system output."""
    def __init__(self):
        pass

    def __enter__(self):
        self.tempout = sys.stdout
        self.temperr = sys.stderr
        sys.stdout = open('/dev/null', 'w')
        sys.stderr = open('/dev/null', 'w')

    def __exit__(self, _type, value, traceback):
        sys.stdout = self.tempout
        sys.stderr = self.temperr


class UserPrivilege(object):
    """A class to be used with Python "with" statement, to use user privilege for the execution
    of the code enclosed by the "with" statement.
    """
    def __init__(self):
        self.was_sudo = False

    def __enter__(self):
        if os.geteuid() == 0:
            os.setegid(int(os.environ['SUDO_GID']))
            os.seteuid(int(os.environ['SUDO_UID']))
            self.was_sudo = True

    def __exit__(self, type, value, traceback):
        if self.was_sudo:
            os.seteuid(0)
            os.setegid(0)


class SudoPrivilege(object):
    """A class to be used with Python "with" statement, to temporarily increase to sudo privilege
    for the execution of code enclosed by the "with" statement.

    NOTE: the script can only gain sudo if the user sudo execute the script in the first place.
    """
    def __init__(self):
        self.has_sudo = os.getenv('SUDO_COMMAND') is not None
        self.was_user = False

    def __enter__(self):
        if not self.has_sudo:
            print_error('Permission denied')
            return
        if os.geteuid() != 0:
            os.seteuid(0)
            os.setegid(0)
            self.was_user = True

    def __exit__(self, type, value, traceback):
        if self.was_user:
            os.setegid(int(os.environ['SUDO_GID']))
            os.seteuid(int(os.environ['SUDO_UID']))
            self.was_user = False


def sudo(f, *args, **kwargs):
    with SudoPrivilege():
        return f(*args, **kwargs)


def find_files(pattern, path=os.curdir, ignore_dirs=None, sort_key=None):
    """Recursively find all files matching supplied filename pattern in the specified path.

    - pattern: filename matching shell pattern as in 'ls' command, eg. '\*.txt'
    - path: a pathname, can be relative or absolute pathname.
    - ignore_dirs: a list of name of dirs under the specified path, to be skipped.
    """
    if ignore_dirs is None:
        ignore_dirs = []
    filenames = []
    for pathname, subdirs, files in os.walk(os.path.abspath(path)):
        # change the mutable subdirs, so os.walk won't walk in the ignored dir.
        for x in ignore_dirs:
            if x in subdirs:
                subdirs.remove(x)
        subdirs.sort()
        filenames += sorted([os.path.join(pathname, filename)
                             for filename in fnmatch.filter(files, pattern)],
                            key=sort_key)
    return filenames


def find_dirs(pattern, path=os.curdir, ignore_dirs=None, sort_key=None):
    """Recursively find all sub directories matching supplied filename pattern in the specified path.

    - pattern: directory name matching shell pattern as in 'ls' command
    - path: a pathname, can be relative or absolute pathname.
    - ignore_dirs: a list of name of dirs under the specified path, to be skipped.
    """
    if ignore_dirs is None:
        ignore_dirs = []
    dir_names = []
    for pathname, subdirs, files in os.walk(os.path.abspath(path)):
        # change the mutable subdirs, so os.walk won't walk in the ignored dir.
        for x in ignore_dirs:
            if x in subdirs:
                subdirs.remove(x)
        dir_names += sorted([os.path.join(pathname, filename)
                             for filename in fnmatch.filter(subdirs, pattern)],
                            key=sort_key)
    return dir_names


def create_sharable_file(filename, data):
    """Write to a file that can be read by all."""
    with UserPrivilege():
        with open(filename, 'w') as f:
            f.write(data)
        try:
            # chmod to share DevVM local /tmp across users
            os.chmod(filename, (stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH |
                                stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        except OSError as e:  # OSError: [Errno 1] Operation not permitted
            # If the file is originally created by other, it is R/W for all and the
            # file write is ok. But it can complain for chmod.
            print_warn(e)


def abspath(filepath):
    """Return the absolute pathname for names with '~', '.', '$SRXSRC/obj_sa/bin/flowd'"""
    if '$' in filepath:
        filepath = os.sep.join([os.getenv(x[1:]) if '$' in x else x
                                for x in filepath.split(os.sep)]).replace(os.sep * 2, os.sep)
    if '~' in filepath:
        filepath = os.path.expanduser(filepath)
    return os.path.abspath(filepath)


def setup_interactive_mode(histfile='.python_history', interact=False):
    """Setup interactive mode with tab completion, prompt color, and command history."""
    # tab completion
    if 'libedit' in readline.__doc__:   # Mac
        print('Please intall GNU readline by "sudo easy_install readline", '
              'the libedit readline has caveat that cmd history not showing well with color prompt.')
        readline.parse_and_bind("bind '\t' rl_complete")
    else:
        readline.parse_and_bind("C-o: operate-and-get-next")
        readline.parse_and_bind("tab: complete")
        # color prompt
        sys.ps1 = '\x01\x1b[1;34m\x02>>> \x01\x1b[0m\x02'
        sys.ps2 = '\x01\x1b[1;34m\x02... \x01\x1b[0m\x02'
    # command history
    if histfile:
        # with a histfile, cmd history is saved across sessions.
        # Note, the test case execution is also saved in history file.
        histfile = os.path.expanduser("~" + os.getlogin() + os.sep + histfile)
        readline.set_history_length(500)
        try:
            with UserPrivilege():
                readline.read_history_file(histfile)
        except IOError as e:  # [Errno 13] Permission denied
            print_warn(e)

        def write_history_file():
            try:
                with UserPrivilege():
                    readline.write_history_file(histfile)
            except IOError as ex:  # [Errno 13] Permission denied
                print_warn(ex)
        atexit.register(write_history_file)

    if interact:
        try:
            import IPython
            IPython.embed()
        except ImportError:
            print("Python interactive mode. Note, use ipython for more interactive support.\n")
            code.interact(local=locals())


def h(recent=25):
    """show command history
    recent: number of recent command lines to show.
    """
    length = readline.get_current_history_length()
    start = 0 if length <= recent else (length - recent)
    for x in xrange(start, readline.get_current_history_length()):
        print(readline.get_history_item(x + 1))


def find_existing_daemons(daemon_list):
    """Utility to find any running specified daemons, excluding those potential false matches.

    - daemon_list: a list of daemons to be closed, specified by string name. E.g. ['flowd', 'serviced']
    - return: (daemons, pids), a list of process strings as in "ps -eaf", and a list of their pid.
    """
    if isinstance(daemon_list, str):
        daemon_list = [daemon_list]

    exclude = {'egrep', 'PID', 'sudo', 'vi', 'vim', 'gdb', 'stap', '<defunct>'}
    s = os.popen('sudo ps -eaf | egrep "PID|%s"' % '|'.join(daemon_list)).read()
    pid_col = s.splitlines()[0].split().index('PID')
    daemons = [x for x in s.splitlines() if
               (not exclude.intersection(set(x.split()))) and
               re.search('|'.join(['[/ ]%s( |$)' % y for y in daemon_list]), x)]
    pids = [x.split()[pid_col] for x in daemons]
    return daemons, pids


def close_existing_daemons(daemon_list, verbose=False):
    """Check and close any running specified daemons.

    - daemon_list: a list of daemons to be closed, specified by string name. E.g. ['flowd', 'serviced']
    """
    if isinstance(daemon_list, str):
        daemon_list = [daemon_list]

    daemons, pids = find_existing_daemons(daemon_list)
    for sig in ['SIGINT', 'SIGKILL']:   # Try SIGINT first. If fail, then do SIGKILL.
        if daemons:
            if verbose:
                print_green('These existing processes will be closed with %s:\n%s' %
                            (sig, '\n'.join(daemons)))
            os.popen('sudo kill -s %s %s' % (sig, ' '.join(pids)))
        # confirming the processes are killed
        for i in xrange(5):
            daemons, pids = find_existing_daemons(daemon_list)
            if not daemons:
                break
            else:
                time.sleep(0.1)
        if daemons:
            print_red('Failed to close these processes with %s:\n%s' %
                      (sig, '\n'.join(daemons)))


def exit_handler(handler, *args, **kwargs):
    """Register an exit handler if it is not registered yet.
    The duplication checking is needed for object that can close and re-connect."""
    if (handler, args, kwargs) not in atexit._exithandlers:
        atexit.register(handler, *args, **kwargs)


class Singleton(type):
    """A metaclass to construct its instance class to be singleton, i.e. can only have one
    single instance in a system.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class SingletonPerParam(type):
    """A metaclass to construct its instance class to be singleton per the parameters
    of the class __init__(). E.g. for a ssh class, it will have a singleton connection for each
    ssh host, but the ssh class can have many instance connecting to different hosts.
    """
    _instances = {}

    def __call__(cls, *args, **kwargs):
        key = (cls, args, ','.join(['%s=%s' % (x, kwargs[x]) for x in sorted(kwargs.keys())]))
        if key not in cls._instances:
            cls._instances[key] = super(SingletonPerParam, cls).__call__(*args, **kwargs)
        return cls._instances[key]


class LazyProperty(object):
    """A decorator to defer expensive evaluation of an object attribute, i.e. lazy evaluation.
    The decorated property should represent non-mutable data, as it replaces itself.

    The expensive evaluation should be defined as a function with same name of the property.
    When the object property is first time used, the evalution is carried out, and then
    the function itself is replaced by the value it returned. Then the function and the
    LazyProperty object are garbage collected, and subsequent use of the property will
    directly refer the value.
    """

    precall = None
    """precall: string name of a obj method, that should be excuted before calling the prop_eval."""

    def __init__(self, prop_eval):
        self.prop_eval = prop_eval

    def __get__(self, obj, cls):
        if obj is None:
            return None
        if self.precall:
            getattr(obj, self.precall)()
        value = self.prop_eval(obj)
        setattr(obj, self.prop_eval.__name__, value)
        return value


class PropertyAfterConnection(LazyProperty):
    """A LazyProperty decorator to decorate those properties only available after
    obj._connect() is being called once.
    """
    precall = '_connect'


class NonblockStdin(object):
    __metaclass__ = Singleton
    """A singleton non-blocking fd of /dev/tty, to poll stdin without blocking.
    As it is a separate fd of /dev/tty, it won't affect the sys.stdin/stdout/stderr fcntl flags.
    """
    def __init__(self):
        self.stdin = open('/dev/tty', 'rb')
        tty_nonblocking(self.stdin)
        # make stdout unbuffered, similar to python -u, otherwise input are echoed only when Enter key is hit.
        # This is only needed for once, and repeating it causes error. Singleton ensures this single execution.
        sys.stdout.flush()
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)


class Verbose(object):
    __metaclass__ = Singleton
    """A class for verbose level control. State can be shared as a singleton object."""
    RESULT_ONLY = 0
    SHOW_FAIL = 1
    SHOW_LOG = 2
    SHOW_TRAFFIC = 3
    SHOW_BACKEND = 4

    def __init__(self, verbose_level=SHOW_TRAFFIC):
        self.level = verbose_level

    def __eq__(self, level):
        return self.level == level

    def __ne__(self, level):
        return self.level != level

    def __lt__(self, level):
        return self.level < level

    def __le__(self, level):
        return self.level <= level

    def __gt__(self, level):
        return self.level > level

    def __ge__(self, level):
        return self.level >= level


class RunParallel(object):
    """A class to be used with Python "with" statement, to run a task in separate process, for
    parallel execution. Eg::

        with RunParallel(func, *args, **kwargs) as my:
            do_something_else()

        o, e, r = my.result

    - func: a function to be executed in parellel
    - \*args, \*\*kwargs: the function's argument parameters
    - return: namedtuple (o, e, r), the stdout output, stderr output, and the func's return value.

    NOTE::

        - For any tentacles to be used in the child process, they should be connected in the parent
          process, so that they can be re-used and can be properly closed at program exit.
        - To avoid mixed print, console output of child process is buffered and printed after child
          process is done. The parent output is printed at real time.
    """
    def __init__(self, func, *args, **kwargs):
        def task(pipe, xfunc, xargs, xkwargs):
            capturor = OutputCapturor(sys.stdout.fileno(), swap=True, hide=True)
            err_capt = OutputCapturor(sys.stderr.fileno(), swap=True, hide=True)
            try:
                rtn = xfunc(*xargs, **xkwargs)
            finally:
                capturor.restore_sys_output()
                err_capt.restore_sys_output()
            pipe.send([capturor.get_buf(), err_capt.get_buf(), rtn])

        self.func = func
        self.name = '%s(*%s, **%s)' % (self.func.__name__, args, kwargs)
        parent_conn, child_conn = multiprocessing.Pipe()
        self.pipe = parent_conn
        self.process = multiprocessing.Process(target=task, args=(child_conn, func, args, kwargs))
        self.result = None

    def __enter__(self):
        self.process.start()
        return self

    def __exit__(self, _type, value, traceback):
        # wait till the child process is done.
        self.process.join()
        # print the output from the child process.
        if self.pipe.poll():
            o, e, rtn = self.pipe.recv()
            self.result = Namedtuple_oer(no_color(o), no_color(e), rtn)
            if o:
                print_green('stdout output from %s' % self.name)
                print(o)
            if e:
                print_error('stderr output from %s' % self.name)
                print(e)
        else:
            print_error('Fail to execute in parallel, %s' % self.name)
        self.pipe.close()


Namedtuple_oe = namedtuple('Namedtuple_oe', ['o', 'e'])
Namedtuple_oe.__repr__ = lambda x: ''


def return_o_e(func):
    """Decorator to convert return values to namedtuple(o, e)."""
    @wraps(func)
    def inner_func(*args, **kwargs):
        oe = func(*args, **kwargs)
        return Namedtuple_oe(*oe) if isinstance(oe, tuple) and len(oe) == 2 else oe
    return inner_func


Namedtuple_oer = namedtuple('Namedtuple_oer', ['o', 'e', 'r'])
Namedtuple_oer.__repr__ = lambda self: colored('Result: %s' % self.r, 'green' if self.r else 'red')


def return_o_e_r(func):
    """Decorator to convert return values to namedtuple(o, e, r)."""
    @wraps(func)
    def inner_func(*args, **kwargs):
        oer = func(*args, **kwargs)
        return Namedtuple_oer(*oer) if isinstance(oer, tuple) and len(oer) == 3 else oer
    return inner_func


## unit test
if __name__ == '__main__':

    # TODO: move to unitests framework.

    # test singleton
    k1 = Verbose()
    k2 = Verbose()
    assert k1 is k2

    # test lazy evaluation
    class TestLazy(object):
        count = 0

        @PropertyAfterConnection
        def dp_mac(self):
            return self.dp_mac

        def _connect(self):
            assert self.count == 0
            self.count += 1
            print("Now, connecting...")
            self.dp_mac = 'LazyEvaluated'

    t = TestLazy()
    print('First time referencing t.dp_mac: %s, it will auto trigger t._connect()' % t.dp_mac)
    print('Second time referencing t.dp_mac: %s, it will not call _connect again.' % t.dp_mac)
    assert t.dp_mac == 'LazyEvaluated'

    # test color and pause_for_a_key().
    print_red('print red.')
    print_green('print green.')
    pause_for_a_key()
    print_green('test done.')
