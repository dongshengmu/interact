# Interactive

A Python package to interact with any program or device with a command line console.

Interactive is an interactive subprocess, it supports programmable console input/output
communication in real-time, direct connection to the console terminal, and
can run programs in parallel and check their output at anytime.


## Features

* Programmable interaction.

```Python
from Interactive import interact, pyssh, util
# Start a interactive subprocess of "ssh root@my_server", if there is no ssh key pair setup, the terminal will be piped 
# for manual password prompt. Optionally, use the sshpass to skip the manual password prompt.
myssh = pyssh.SshSession('my_server', 'root', sshpass=None)
# Run a command via the ssh connection and print the output locally.
myssh.cmd('ls -ltr')
# Execute a command at the server via ssh connection, and save the output from stdout/stderr for further processing.
output, erroutput = myssh.cmd('cat ~/mydoc.txt')
```

* Direct console.

```Python
# Pipe to the ssh raw terminal, all native key strokes are supported, and interactive programs (eg. top) are supported.
# Use Ctrl-] to switch back.
myssh.console()
```

* Run programs in parallel and check their output at anytime.

```Python
>>> with my_server.background_proc('tail -f /var/log/my_task.log') as bg:
...     print('This printing is in main process, while a continuous execution is running  runs in another process.')
...     # do something else in parallel
>>> print('Here is the output got from my_server while we are doing something in front end.\n%s' % bg.o)
>>>
# start a program at the remote server
>>> o, e = my_server.cmd('ping 2.2.2.2', expect=None, timeout=0)
ping 2.2.2.2
# check any output got so far
>>> o, e = my_server.check_outputs()
ping 2.2.2.2
PING 2.2.2.2 (2.2.2.2) 56(84) bytes of data.
64 bytes from 2.2.2.2: icmp_seq=1 ttl=63 time=1.90 ms
64 bytes from 2.2.2.2: icmp_seq=2 ttl=63 time=2.26 ms
64 bytes from 2.2.2.2: icmp_seq=3 ttl=63 time=1.19 ms
# stop the program with Ctrl-C, and get the remaining output
>>> o, e = my_server.ctrl_c(continuous_output=True)
```

* Interactive with anything with command line interface.

It programmably controls local or remote programs and devices, via their command line console based user interface.
For example, applications use this Interactive package to control gdb for debug automation, to control containers and 
devices for test automation, to ssh or telnet multiple components in a develop environment for DevOp and use as a  
semi-auto workbench environment, to simplify frequent manual command executions or to run commands in scale across 
multiple devices.


## Installation

```
$ sudo easy_install interactive
or
$ sudo pip install interactive
```
