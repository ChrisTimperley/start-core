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

import configparser

from .scenario import Scenario
from .exceptions import FileNotFoundException

try:
    DEVNULL = subprocess.DEVNULL
except AttributeError:
    DEVNULL = open(os.devnull, 'w')


@attr.s(frozen=True)
class SITL(object):
    fn_binary = attr.ib(type=str)
    fn_harness = attr.ib(type=str)
    vehicle = attr.ib(type=str)
    home = attr.ib(type=Tuple[float, float, float, float])

    @staticmethod
    def from_scenario(scenario):
        # type: (Scenario) -> SITL
        home = scenario.mission.home  # FIXME alias
        name_binary = ({
            'APMrover2': 'ardurover',
            'ArduCopter': 'arducopter',
            'ArduPlane': 'arduplane'
        })[scenario.mission.vehicle]
        dir_base = scenario.directory
        fn_binary = os.path.join(dir_base, 'build/sitl/bin', name_binary)
        # FIXME allow a custom script to be used?
        fn_harness = os.path.join(dir_base, 'Tools/autotest/sim_vehicle.py')
        return SITL(fn_binary,
                    fn_harness,
                    scenario.vehicle,
                    scenario.mission.home)

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
            "-l", "{},{},{},{}".format(*self.__home_loc),
            "-v", self.__vehicle,
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
            process = subprocess.Popen(command,
                                       shell=True,
                                       stdin=DEVNULL,
                                       stdout=DEVNULL,
                                       stderr=DEVNULL,
                                       preexec_fn=os.setsid)
            yield
        finally:
            if process:
                os.killpg(self.__process.pid, signal.SIGTERM)
