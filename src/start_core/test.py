"""
This module is responsible for implementing a GenProg-style test harness for
a given scenario.
"""
__all__ = ['execute']

from typing import Tuple
import logging

import dronekit

from .sitl import SITL
from .mission import Mission
from .attack import Attack, Attacker
from .exceptions import TimeoutException

logger = logging.getLogger(__name__)  # type: logging.Logger
logger.setLevel(logging.DEBUG)


def execute(sitl,                   # type: SITL
            mission,                # type: Mission
            attack=None,            # type: Optional[Attack]
            speedup=1,              # type: int
            prefix='',              # type: str
            timeout_mission=240,    # type: int
            timeout_liveness=1,     # type: int
            timeout_connection=10,  # type: int
            port_attacker=14300,    # type: int
            check_wps=False,        # type: bool
            enable_workaround=True  # type: bool
            ):                      # type: (...) -> Tuple[bool, str]
    """
    Executes the test.

    Parameters:
        sitl_prefix: a command to prefix to the SITL binary. (used to
            attach valgrind, for example).
        speedup: the speedup factor that should be used by the simulator.

    Returns:
        a tuple of the form `(passed, reason)`, where `passed` is a flag
        that indicates whether or not the test succeeded, and `reason` is
        an optional string that is used to describe the reason for the
        test failure (if indeed there was a failure).
    """
    vehicle = None
    if attack:
        attacker = Attacker(attack, sitl.url, port_attacker)
    else:
        attacker = None

    try:
        with sitl.launch(prefix, speedup):
            if attacker:
                attacker.prepare()

            # NOTE dronekit is broken!
            #      it always tries to connect to 127.0.0.1:5760
            logger.debug("trying to connect to vehicle [%s]", sitl.url)
            vehicle = dronekit.connect(sitl.url,
                                       wait_ready=False,
                                       heartbeat_timeout=timeout_connection)
            logger.debug("established connection with vehicle.")
            logger.debug("waiting for vehicle to be ready.")
            vehicle.wait_ready(True, timeout=timeout_connection)
            logger.debug("vehicle is ready for mission.")

            # launch the attack, if one was provided
            if attacker:
                logger.debug("launching attack on vehicle")
                attacker.start()
                logger.debug("launched attack on vehicle")
            else:
                logger.debug("skipping attack launch: no attack provided.")

            # execute the mission
            return mission.execute(time_limit=timeout_mission,
                                   conn=vehicle,
                                   speedup=speedup,
                                   timeout_heartbeat=timeout_liveness,
                                   enable_workaround=enable_workaround,
                                   check_wps=check_wps)
    except TimeoutException:
        return (False, "timeout occurred")
    finally:
        if attacker:
            logger.debug("closing attack server")
            attacker.stop()
            logger.debug("closed attack server")
        if vehicle:
            logger.debug("closing connection to vehicle")
            vehicle.close()
            logger.debug("closed connection to vehicle")
