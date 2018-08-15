__all__ = ['Attack', 'Attacker']

import subprocess
import signal
import socket
import os
import tempfile
import time

import attr
import configparser


@attr.s(frozen=True)
class Attack(object):
    """
    Provides an immutable description of an attack (i.e., an exploit) that may
    be performed.
    """
    script = attr.ib(type=str)
    flags = attr.ib(type=str)
    longitude = attr.ib(type=float)
    latitude = attr.ib(type=float)
    radius = attr.ib(type=float)


class Attacker(object):
    """
    Responsible for launching a given attack on a vehicle.
    """
    def __init__(self,
                 attack,    # type: Attack
                 url_sitl,  # type: str
                 port       # type: int
                 ):         # type: (...) -> None
        self.__attack = attack
        self.__url_sitl = url_sitl
        self.__port = port

        # FIXME I can't find any documentation or examples for this parameter.
        # The default value in START is -1.
        # From looking at an example attack script, it would seem that this
        # parameter specifies the number of seconds to wait before reporting an
        # attack to the attack server. If set to -1, the attack won't be
        # reported. Presuming that only successful attacks are reported (rather
        # than all attempted attacks), then we probably want the timeout to be
        # zero, since we want to prevent the attack.
        self.__report = 0 # FIXME

        self.__fn_log = None
        self.__fn_mav = None
        self.__connection = None
        self.__socket = None
        self.__process = None

    def prepare(self):  # type: () -> None
        attack = self.__attack
        self.__fn_log = tempfile.NamedTemporaryFile()
        self.__fn_mav = tempfile.NamedTemporaryFile()

        cmd = [
            'python',
            attack.script,
            "--master=udp:{}".format(self.__url_sitl),
            "--baudrate=115200",
            "--port={}".format(self.__port),
            "--report-timeout={}".format(self.__report),
            "--logfile={}".format(self.__fn_log.name),
            "--mavlog={}".format(self.__fn_mav.name)
        ]

        if self.__script_flags != '':
            tokens = attack.flags.split(",")
            cmd.extend(tokens)

        cmd.extend([attack.latitude, attack.longitude, attack.radius])
        cmd = [str(s) for s in cmd]
        cmd = ' '.join(cmd)

        # launch server
        print(cmd)
        self.__process = subprocess.Popen(cmd,
                                          shell=True,
                                          preexec_fn=os.setsid)
                                          # stdout=subprocess.PIPE,
                                          # stderr=subprocess.STDOUT)

        # connect
        self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        time.sleep(2) # TODO hacky?
        self.__socket .connect(("0.0.0.0", self.__port))
        self.__connection = self.__socket.makefile()

    def start(self):  # type: () -> None
        self.__connection.write("START\n")
        self.__connection.flush()

    def stop(self):  # type: () -> None
        # close connection
        if self.__connection:
            self.__connection.write("EXIT\n")
            self.__connection.flush()
            self.__connection.close()
            self.__connection = None

        # close socket
        if self.__socket:
            self.__socket.close()
            self.__socket = None

        # TODO why was there a timeout here?

        # kill server
        if self.__process:
            os.killpg(self.__process.pid, signal.SIGKILL) # FIXME use SIGTERM
            self.__process = None

        # destroy temporary files
        self.__fn_log = None
        self.__fn_mav = None

    def was_successful(self):  # type: () -> bool
        self.__connection.write("CHECK\n")
        self.__connection.flush()

        reply = self.__connection.readline().strip()
        return "NO" not in reply
