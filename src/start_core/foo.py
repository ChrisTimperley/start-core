import os
import logging

from .test import execute
from .scenario import Scenario


def main():
    log_to_stdout_formatter = logging.Formatter(
        '%(asctime)s:%(levelname)s: %(message)s',
        '%Y-%m-%d %H:%M:%S')
    log_to_stdout = logging.StreamHandler()
    log_to_stdout.setLevel(logging.DEBUG)
    log_to_stdout.setFormatter(log_to_stdout_formatter)
    logging.getLogger('start_core').addHandler(log_to_stdout)

    fn_scenario = "/home/chris/start/scenarios/AIS-Scenario1/scenario.config"
    scenario = Scenario.from_file(fn_scenario)
    (passed, reason) = execute(sitl=scenario.sitl,
                               mission=scenario.mission,
                               attack=scenario.attack,
                               speedup=10,
                               timeout_mission=300,
                               timeout_liveness=5,
                               timeout_connection=10,
                               check_wps=True)
