#!/usr/bin/env python
#
# This file is responsible for implementing a GenProg-style test harness for
# a given scenario.
#
from __future__ import print_function
import math
import sys
import os
import configparser
import pprint
import argparse

import dronekit

import sitl
import mission
import attack
import helper


class TestCase(object):
    def __init__(self,
                 fn_mission, # type: str
                 use_attacker = False, # type: Optional[bool]
                 fn_cfg_scenario = None, # type: Optional[str]
                 fn_cfg_default = None, # type: Optional[str]
                 dir_source = '/opt/ardupilot', # type: Optional[str],
                 connection_timeout = 10, # type: Optional[int],
                 home = None # type: Optional[Tuple[float, float, float, float]]
                 ): # type: None
        """
        Constructs a new test case.

        Parameters:
            end_pos: the expected position of the vehicle following the
                completion of the test.
            use_attacker: a flag indicating whether this test case should
                perform the attack.

        TODO:
            accept a scenario file
        """
        if not fn_cfg_scenario:
            fn_cfg_scenario = "/experiment/config/scenario.cfg"
        if not fn_cfg_default:
            fn_cfg_default = "/experiment/config/default.cfg"

        assert os.path.isfile(fn_cfg_scenario), \
            "could not find scenario config: {}".format(fn_cfg_scenario)
        assert os.path.isfile(fn_cfg_default), \
            "could not find default config: {}".format(fn_cfg_default)

        self.__connection_timeout = connection_timeout

        # load the config file for this scenario
        self.__cfg = configparser.SafeConfigParser()
        self.__cfg.read(fn_cfg_default)
        self.__cfg.read(fn_cfg_scenario)

        self.__sitl = sitl.SITL.from_cfg(self.__cfg,
                                         dir_source=dir_source,
                                         home=home)
        self.__mission = \
            mission.Mission.from_file(home_location=self.__sitl.home,
                                      vehicle_kind=self.__sitl.vehicle,
                                      fn=fn_mission)

        if use_attacker:
            self.__attacker = attack.Attacker.from_cfg(self.__cfg)
        else:
            self.__attacker = None

    def execute(self,
                sitl_prefix = None,
                speedup = 1,
                time_limit = 240,
                liveness_timeout = 1,
                check_wps = False,
                enable_workaround = True
                ):
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
        # sitl, vehicle, attacker
        trace = []
        vehicle = None
        try:
            # let's prep the attack server
            if self.__attacker:
                self.__attacker.prepare()

            self.__sitl.start(prefix=sitl_prefix,
                              speedup=speedup)

            # connect to the vehicle
            # dronekit is broken! it always tries to connect to 127.0.0.1:5760
            print("try to connect to vehicle...")
            print("connection timeout: %s" % self.__connection_timeout)
            dronekit_connects_to = 'udp:127.0.0.1:14550'
            vehicle = dronekit.connect(dronekit_connects_to,
                                       wait_ready=False,
                                       heartbeat_timeout=self.__connection_timeout)
            vehicle.wait_ready(True, timeout=self.__connection_timeout)
            print("connected")

            # launch the attack, if enabled
            if self.__attacker:
                self.__attacker.start()

            print("Using mission execution time limit: {} seconds".format(time_limit))
            return self.__mission.execute(time_limit=time_limit,
                                          vehicle=vehicle,
                                          speedup=speedup,
                                          timeout_heartbeat=liveness_timeout,
                                          enable_workaround=enable_workaround,
                                          check_wps=check_wps)

        except mission.TimeoutError:
            return (False, "timeout occurred")
        finally:
            if self.__attacker:
                self.__attacker.stop()
            if vehicle:
                vehicle.close()
            self.__sitl.stop()
