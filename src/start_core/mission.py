"""
FIXME inconsistency in storage of home location
"""
from __future__ import print_function
__all__ = ['Mission']

from typing import List, Tuple
from timeit import default_timer as timer
import time
import signal
import logging

import dronekit
import attr

from .exceptions import TimeoutException
from .helper import distance, observe

logger = logging.getLogger(__name__)  # type: logging.Logger
logger.setLevel(logging.DEBUG)


def parse_command(s):
    """
    Parses a line from a mission file into its corresponding Command
    object in Dronekit.
    """
    args = s.split()
    arg_index = int(args[0])
    arg_currentwp = 0 # int(args[1])
    arg_frame = int(args[2])
    arg_cmd = int(args[3])
    arg_autocontinue = 0 # not supported by dronekit
    (p1, p2, p3, p4, x, y, z) = [float(x) for x in args[4:11]]
    cmd = dronekit.Command(
        0, 0, 0, arg_frame, arg_cmd, arg_currentwp, arg_autocontinue,
        p1, p2, p3, p4, x, y, z)
    return cmd


@attr.s(frozen=True)
class Oracle(object):
    """
    Describes the expected outcome of a mission execution.
    """
    num_waypoints_visited = attr.ib(type=int)
    end_position = attr.ib(type=dronekit.LocationGlobal)
    max_distance = attr.ib(type=float)

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

        # FIXME hardcoded maximum distance
        oracle = Oracle(num_wps, end_position, 3.0)
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
    def from_file(home,     # type: Tuple[float, float, float, float]
                  vehicle,  # type: str
                  fn        # type: str
                  ):        # type: (...) -> Mission
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
                conn,               # type: dronekit.Vehicle
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
            logging.debug("adjusting time limit due to speedup > 1")
            logging.debug("")
            time_limit_old = time_limit
            time_limit = int(time_limit / speedup) + 10
            logging.debug("adjusted time limit: %d seconds -> %d seconds",
                          time_limit_old, time_limit)
        logging.debug("using wall-clock time limit: %d seconds", time_limit)

        def timeout_handler(signum, frame):
            raise TimeoutException
        logging.debug("adding timeout signal handler")
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(time_limit)
        logging.debug("added timeout signal handler")

        logging.debug("waiting for vehicle to become armable")
        while not conn.is_armable:
            time.sleep(0.2)
        logging.debug("vehicle is armable")

        logging.debug("attempting to arm vehicle")
        conn.armed = True
        while not vehicle.armed:
            time.sleep(0.1)
            conn.armed = True
        logging.debug("vehicle is armed")

        self.issue(conn, enable_workaround)

        logging.debug("switching vehicle mode to AUTO")
        conn.mode = dronekit.VehicleMode("AUTO")
        logging.debug("switched vehicle mode to AUTO")
        logging.debug("sending mission start message to vehicle")
        message = conn.message_factory.command_long_encode(
            0, 0, 300, 0, 1, len(self) + 1, 0, 0, 0, 0, 4)
        conn.send_mavlink(message)
        logging.debug("sent mission start message to vehicle")

        # monitor the mission
        mission_complete = [False]
        actual_num_wps_visited = [0]
        expected_num_wps_visited = self.__expected_num_wps_visited
        is_copter = self.vehicle == 'ArduCopter'
        pos_last = vehicle.location.global_frame
        logging.debug("Vehicle is expected to visit at least %d WPs",
                      self.oracle.num_waypoints_visited)

        try:
            def on_waypoint(self, name, message):
                text = message.text
                logging.debug("received STATUSTEXT from vehicle: %s", text)
                if text.startswith("Reached waypoint #") or \
                   text.startswith("Reached command #") or \
                   text.startswith("Skipping invalid cmd"):
                    actual_num_wps_visited[0] += 1
                    logging.debug("incremented number of visited waypoints")

                if text.startswith("Reached destination") or \
                   text.startswith("Mission Complete") or \
                   (text.startswith("Disarming motors") and is_copter):
                    logging.debug("message indicates end of mission")
                    actual_num_wps_visited[0] += 1
                    pos_last = conn.location.global_frame
                    mission_complete[0] = True
                    logging.debug("marked mission as complete")
                    logging.debug("incremented number of visited waypoints")

            logging.debug("attempting to attach STATUSTEXT listener")
            conn.add_message_listener('STATUSTEXT', on_waypoint)
            logging.debug("attached STATUSTEXT listener")

            # wait until the last waypoint is reached, the time limit has
            # expired, or the attack was successful
            logging.debug("waiting for mission to terminate")
            while not mission_complete[0]:
                if conn.last_heartbeat > timeout_heartbeat:
                    logging.debug("vehicle became unresponsive (heartbeat timeout: %.2f seconds)",
                                  timeout_heartbeat)
                    return (False, "vehicle became unresponsive.")

                # lat = vehicle.location.global_frame.lat
                # lon = vehicle.location.global_frame.lon
                # alt = vehicle.location.global_frame.alt
                # print("Pos: {:.6f}, {:.6f}, {:.3f}".format(lat, lon, alt))
                time.sleep(0.2)

            logging.debug("mission has terminated")
            actual_num_wps_visited = actual_num_wps_visited[0]
            logging.debug("visited %d waypoints (expected >= %d waypoints)",
                          actual_num_wps_visited,
                          self.oracle.num_waypoints_visited)

            if check_wps:
                logging.debug("checking waypoints against oracle")
            else:
                logging.debug("ignoring visited waypoints")

            sat_wps = actual_num_wps_visited >= self.oracle.num_waypoints_visited
            if check_wps and sat_wps:
                logging.debug("vehicle failed to visit the minimum required number of WPs")
                return (False, "vehicle didn't visit all of the WPs")

            state = observe(conn)
            logging.debug("final state of vehicle: %s", state)
            dist = distance(self.oracle.end_position, pos_last)
            logging.debug("distance to expected end position: %.3f metres", dist)

            if dist > self.oracle.max_distance:
                logging.debug("vehicle successfully executed the mission")
                return (True, None)
            else:
                logging.debug("distance to expected end position exceeded maximum (%.3f metres)",
                              self.oracle.max_distance)
                return (False, "vehicle was too far away from expected end position")

        finally:
            logging.debug("removing STATUSTEXT listener")
            conn.remove_message_listener('STATUSTEXT', on_waypoint)
            logging.debug("removed STATUSTEXT listener")
