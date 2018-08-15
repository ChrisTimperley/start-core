"""
This module is responsible for launching, closing, and interacting with the
SITL for the ArduPilot.
"""
__all__ = ['SITL']

from typing import Tuple
import subprocess
import os
import signal
import contextlib
import logging

import configparser

from .scenario import Scenario
from .mission import Mission
from .exceptions import FileNotFoundException

logger = logging.getLogger(__name__)  # type: logging.Logger
logger.setLevel(logging.DEBUG)

try:
    DEVNULL = subprocess.DEVNULL
except AttributeError:
    DEVNULL = open(os.devnull, 'w')


@attr.s(frozen=True)
class SITL(object):
    fn_harness = attr.ib(type=str)
    vehicle = attr.ib(type=str)
    home = attr.ib(type=Tuple[float, float, float, float])

    @property
    def url(self):  # type: () -> str
        return 'udp:127.0.0.1:14550'

    def command(self,
                prefix=None,    # type: Optional[str]
                speedup=1       # type: int
                ):              # type: (...) -> str
        """
        Computes the command that should be used to launch the SITL.

        Parameters:
            prefix: an optional prefix that should be attached to the command.
            speedup: the speedup factor that should be applied to the simulator
                clock.
        """
        if prefix is None:
            prefix = ''
        cmd = [
            prefix,
            self.fn_harness,
            "--mavproxy-args '--daemon --out 127.0.0.1:14552 --out 127.0.0.1:14553'", # don't attach to STDIN!
            "-l", "{},{},{},{}".format(*self.home),
            "-v", self.vehicle,
            "-w",
            "--speedup={}".format(speedup),
            "--no-rebuild "
        ]
        return ' '.join(cmd).lstrip()

    @contextlib.contextmanager
    def launch(self,
               prefix=None, # type: Optional[str]
               speedup=1    # type: int
               ):           # type: (...) -> None
        command = self.command(prefix, speedup)
        process = None  # type: Optional[subprocess.Popen]
        try:
            logger.debug("launching SITL via command: %s", command)
            process = subprocess.Popen(command,
                                       shell=True,
                                       stdin=DEVNULL,
                                       stdout=DEVNULL,
                                       stderr=DEVNULL,
                                       preexec_fn=os.setsid)
            logger.debug("launched SITL")
            yield
        finally:
            if process:
                logger.debug("sending SIGTERM to SITL process [%d]", process.pid)
                os.killpg(process.pid, signal.SIGTERM)
                logger.debug("sent SIGTERM to SITL process [%d]", process.pid)
