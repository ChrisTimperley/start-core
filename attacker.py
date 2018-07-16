import subprocess
import signal
import socket
import os
import tempfile
import time


class Attacker(object):
    @staticmethod
    def from_cfg(cfg):
        return Attacker(script='attack.py',
                        flags=cfg.get('Attack', 'script_flags'),
                        longitude=cfg.getfloat('Attack', 'longitude'),
                        latitude=cfg.getfloat('Attack', 'latitude'),
                        radius=cfg.getfloat('Attack', 'radius'),
                        port=16666, # we can just run the attack server on a fixed port
                        url_sitl='127.0.0.1:14551') # FIXME the SITL should also be at a fixed URL

    def __init__(self,
                 script,
                 flags,
                 longitude,
                 latitude,
                 radius,
                 url_sitl,
                 port):
        self.__script = "/experiment/attack.py" # script
        self.__url_sitl = url_sitl
        self.__port = port
        self.__script_flags = flags.strip()
        self.__longitude = longitude
        self.__latitude = latitude
        self.__radius = radius
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

    def prepare(self):
        self.__fn_log = tempfile.NamedTemporaryFile()
        self.__fn_mav = tempfile.NamedTemporaryFile()

        cmd = [
            'python',
            self.__script,
            "--master=udp:{}".format(self.__url_sitl),
            "--baudrate=115200",
            "--port={}".format(self.__port),
            "--report-timeout={}".format(self.__report),
            "--logfile={}".format(self.__fn_log.name),
            "--mavlog={}".format(self.__fn_mav.name)
        ]

        if self.__script_flags != '':
            tokens = self.__script_flags.split(",")
            cmd.extend(tokens)

        cmd.extend([self.__latitude, self.__longitude, self.__radius])
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

    def start(self):
        self.__connection.write("START\n")
        self.__connection.flush()

    def stop(self):
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

    def was_successful(self):
        self.__connection.write("CHECK\n")
        self.__connection.flush()

        reply = self.__connection.readline().strip()
        return "NO" not in reply
