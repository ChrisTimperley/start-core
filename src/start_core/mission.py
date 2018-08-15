"""
FIXME inconsistency in storage of home location
"""
__all__ ['Mission']

from __future__ import print_function
from typing import List
from timeit import default_timer as timer
import time
import signal
import logging

import dronekit
from dronekit import Command, VehicleMode

import helper

from .exceptions import TimeoutException

logger = logging.getLogger(__name__)  # type: logging.Logger
logger.setLevel(logging.DEBUG)


def parse_command(s):
    """
    Parses a line from a mission file into its corresponding Command
    object in Dronekit.
    """
    args = s.split()
    arg_index = int(args[0])
    arg_currentwp = 0 #int(args[1])
    arg_frame = int(args[2])
    arg_cmd = int(args[3])
    arg_autocontinue = 0 # not supported by dronekit
    (p1, p2, p3, p4, x, y, z) = [float(x) for x in args[4:11]]
    cmd = Command(0, 0, 0, arg_frame, arg_cmd, arg_currentwp, arg_autocontinue,\
                  p1, p2, p3, p4, x, y, z)
    return cmd


@attr.s(frozen=True)
class Oracle(object):
    """
    Describes the expected outcome of a mission execution.
    """
    num_waypoints_visited = attr.ib(type=int)
    end_position = attr.ib(type=dronekit.LocationGlobal)

    @staticmethod
    def build(conn,                 # type: dronekit.Vehicle
              vehicle,              # type: str
              home,                 # type: Tuple[float, float, float, float]
              enable_workaround     # type: bool
              ):                    # type: (...) -> Oracle
        num_wps = 0
        home_loc = dronekit.LocationGlobal(home[0], home[1], home[2])
        end_position = home_loc

        for command in conn.commands:
            # assumption: all commands use the same frame of reference
            # TODO add assertion
            command_id = command.command

            # TODO tweak logic for copter/plane/rover
            if command_id == 16: # MAV_CMD_NAV_WAYPOINT
                end_position = \
                    dronekit.LocationGlobal(command.x, command.y, command.z)
                on_ground = False

            elif command_id == 20: # MAV_CMD_NAV_RETURN_TO_LAUNCH:
                end_position = home_loc
                on_ground = True

                # copter will ignore all commands after an RTL
                if vehicle == 'ArduCopter':
                    num_wps += 1
                    break

            # NOTE if the vehicle is instructed to land whilst already on the
            #      ground, then the rest of the mission will be ignored.
            elif command_id == 21 and enable_workaround and on_ground: # MAV_CMD_NAV_LAND
                break

            num_wps += 1

        # first WP is completely ignored by ArduCopter
        if vehicle == 'ArduCopter':
            num_wps -= 1

        oracle = Oracle(num_wps, end_position)
        logging.debug("generated oracle: %s", oracle)
        return oracle


# @attr.s(frozen=True)
class Mission(object):
    """
    Describes a mission that may be assigned to an ArduPilot vehicle.
    """
    vehicle = attr.ib(type=str)  # FIXME use Enum?
    commands = attr.ib(type=List[dronekit.Command])
    home = attr.ib(type=Tuple[float, float, float, float])

    @staticmethod
    def from_file(home,             # type: Tuple[float, float, float, float]
                  vehicle_kind,     # type: str
                  fn                # type: str
                  ):                # type: (...) -> Mission
        cmds = []
        with open(fn, 'r') as f:
            lines = [l.strip() for l in f]
            for line in lines[1:]:
                cmd = parse_command(line)
                cmds.append(cmd)
        return Mission(vehicle, cmds, home)

    def __len__(self):
        """
        The length of the mission is given its number of commands.
        """
        return len(self.__commands)

    def issue(self,
              conn,                 # type: dronekit.Vehicle
              enable_workaround     # type: bool
              ):                    # type: (...) -> None
        """
        Issues (but does not trigger) a mission, provided as a list of commands,
        to a given vehicle.
        Blocks until the mission has been downloaded onto the vehicle.
        """
        vcmds = conn.commands
        logger.debug("clearing vehicle's command list")
        vcmds.clear()
        logger.debug("cleared vehicle's command list")
        logging.debug("adding commands to vehicle's command list")
        for command in self.commands:
            vcmds.add(command)
            logging.debug("added command to list: %s", command)
        logging.debug("added all commands to vehicle's command list")

        # FIXME lift into constructor
        logging.debug("computing oracle for mission")
        self.oracle = Oracle(conn, self.vehicle, self.home, enable_workaround)
        logging.debug("computed oracle for mission")

        logging.debug("uploading mission to vehicle")
        vcmds.upload()
        logging.debug("triggered upload")
        vcmds.wait_ready()
        logging.debug("finished uploading mission to vehicle")

    def execute(self,
                time_limit,         # type: int
                vehicle,            # type: dronekit.Vehicle
                speedup,            # type: int
                timeout_heartbeat,  # type: int
                check_wps,          # type: bool
                enable_workaround   # type: bool
                ):                  # type: (...) -> List[bool, str]
        """
        Executes this mission on a given vehicle.

        Parameters:
            time_limit: the number of seconds that the vehicle should be given
                to finish executing the mission before aborting the mission.
            vehicle: the vehicle that should execute the mission.
            speedup: the speed-up factor used by the simulation.

        Raises:
            TimeoutError: if the mission doesn't finish executing within the
                given time limit.
        """
        # modify the time limit according to the simulator speed-up
        if speedup > 1:
            time_limit = int((time_limit / speedup) + 10)
            print("using wall-clock time limit: {} seconds".format(time_limit))

        def timeout_handler(signum, frame):
            raise TimeoutException
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(time_limit)

        logging.debug("waiting for vehicle to become armable")
        while not vehicle.is_armable:
            time.sleep(0.2)
        logging.debug("vehicle is armable")

        logging.debug("attempting to arm vehicle")
        vehicle.armed = True
        while not vehicle.armed:
            time.sleep(0.1)
            vehicle.armed = True
        logging.debug("vehicle is armed")

        self.issue(vehicle, enable_workaround)

        logging.debug("switching vehicle mode to AUTO")
        vehicle.mode = VehicleMode("AUTO")
        logging.debug("switched vehicle mode to AUTO")
        logging.debug("sending mission start message to vehicle")
        message = vehicle.message_factory.command_long_encode(
            0, 0, 300, 0, 1, len(self) + 1, 0, 0, 0, 0, 4)
        vehicle.send_mavlink(message)
        logging.debug("sent mission start message to vehicle")

        # monitor the mission
        mission_complete = [False]
        actual_num_wps_visited = [0]
        expected_num_wps_visited = self.__expected_num_wps_visited
        is_copter = self.vehicle == 'ArduCopter'
        pos_last = vehicle.location.global_frame
        print("Expected num. WPS >= {}".format(expected_num_wps_visited))

        # if no communication is received from the vehicle within this length
        # of time, then the mission is considered a failure.
        print("Using heartbeat timeout: {:.3f} seconds".format(timeout_heartbeat))

        try:
            def on_waypoint(self, name, message):
                text = message.text
                # print("STATUSTEXT: {}".format(text))
                if text.startswith("Reached waypoint #") or \
                   text.startswith("Reached command #") or \
                   text.startswith("Skipping invalid cmd"):
                    actual_num_wps_visited[0] += 1

                if text.startswith("Reached destination") or \
                   text.startswith("Mission Complete") or \
                   (text.startswith("Disarming motors") and is_copter):
                    actual_num_wps_visited[0] += 1
                    pos_last = vehicle.location.global_frame
                    mission_complete[0] = True

            vehicle.add_message_listener('STATUSTEXT', on_waypoint)

            # wait until the last waypoint is reached, the time limit has
            # expired, or the attack was successful
            while not mission_complete[0]:
                if vehicle.last_heartbeat > timeout_heartbeat:
                    return (False, "vehicle became unresponsive.")

                # lat = vehicle.location.global_frame.lat
                # lon = vehicle.location.global_frame.lon
                # alt = vehicle.location.global_frame.alt
                # print("Pos: {:.6f}, {:.6f}, {:.3f}".format(lat, lon, alt))

                time.sleep(0.2)

            # unpack
            actual_num_wps_visited = actual_num_wps_visited[0]

            print("Actual # WPs visited = {}".format(actual_num_wps_visited))
            print("Expected # WPs visited >= {}".format(expected_num_wps_visited))

            if check_wps:
                print("checking WPs...")
            else:
                print("not checking WPs")

            if check_wps and actual_num_wps_visited < expected_num_wps_visited:
                return (False, "vehicle didn't visit all of the WPs")

            # observe the final state of the vehicle
            state = helper.snapshot(vehicle)
            dist = helper.distance(self.expected_end_position, pos_last)
            pprint.pprint(state)
            print("Distance to expected end position: {:.3f} metres".format(dist))

            # TODO lift this into the config
            if dist < 3.0:
                return (True, None)
            else:
                return (False, "vehicle was too far away from expected end position")

        # remove the listener
        finally:
            vehicle.remove_message_listener('STATUSTEXT', on_waypoint)
