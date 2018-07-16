from __future__ import print_function
from timeit import default_timer as timer
import time
import signal
import pprint

import dronekit
from dronekit import Command, VehicleMode

import helper


class TimeoutError(Exception):
    pass


class Mission(object):
    @staticmethod
    def __parse_command(s):
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

    @staticmethod
    def from_file(home_location, vehicle_kind, fn):
        """
        Loads a mission from a given WPL file.
        """
        cmds = []
        with open(fn, 'r') as f:
            lines = [l.strip() for l in f]
            for line in lines[1:]:
                cmd = Mission.__parse_command(line)
                cmds.append(cmd)
        return Mission(home_location, cmds, vehicle_kind)

    def __init__(self, home_location, commands, vehicle_kind):
        assert vehicle_kind in ['APMrover2', 'ArduPlane', 'ArduCopter']

        home_lat, home_lon, home_alt = home_location[:3]
        self.__vehicle_kind = vehicle_kind
        self.__home_location = \
            dronekit.LocationGlobal(home_lat, home_lon, home_alt)
        self.__commands = commands[:]

    def __generate_oracle(self, vehicle, enable_workaround):
        """
        Statically determines the expected end position of the vehicle from the
        contents of the mission, as well as the (minimum) number of waypoints
        that the vehicle is expected to visit. The results are stored in
        `self.__expected_end_position` and `self.__expected_num_wps_visited`.

        Parameters:
            vehicle:        a connection to the vehicle under test.
        """

        self.__expected_end_position = self.__home_location
        self.__expected_num_wps_visited = 0
        on_ground = True

        for command in vehicle.commands:
            # assumption: all commands use the same frame of reference
            # TODO add assertion
            command_id = command.command

            # TODO tweak logic for copter/plane/rover
            if command_id == 16: # MAV_CMD_NAV_WAYPOINT
                self.__expected_end_position = \
                    dronekit.LocationGlobal(command.x, command.y, command.z)
                on_ground = False

            elif command_id == 20: # MAV_CMD_NAV_RETURN_TO_LAUNCH:
                self.__expected_end_position = self.__home_location
                on_ground = True

                # copter will ignore all commands after an RTL
                if self.__vehicle_kind == 'ArduCopter':
                    self.__expected_num_wps_visited += 1
                    break

            # NOTE if the vehicle is instructed to land whilst already on the
            #      ground, then the rest of the mission will be ignored.
            elif command_id == 21 and enable_workaround and on_ground: # MAV_CMD_NAV_LAND
                break

            self.__expected_num_wps_visited += 1

        # first WP is completely ignored by ArduCopter
        if self.__vehicle_kind == 'ArduCopter':
            self.__expected_num_wps_visited -= 1

    def __len__(self):
        """
        The length of the mission is given by the number of commands that it
        contains.
        """
        return len(self.__commands)

    @property
    def home_location(self):
        """
        The initial location of the vehicle at the start of the mission.
        """
        return self.__home_location

    @property
    def expected_tokens(self):
        """
        The sequence of tokens that the vehicle is expected to produce during
        this mission.
        """
        return self.__expected_tokens[:]

    @property
    def expected_end_position(self):
        """
        The expected end position of the vehicle upon completion of this
        mission.
        """
        return self.__expected_end_position

    def issue(self, vehicle, enable_workaround):
        """
        Issues (but does not trigger) a mission, provided as a list of commands,
        to a given vehicle.
        Blocks until the mission has been downloaded onto the vehicle.
        """
        vcmds = vehicle.commands
        vcmds.clear()
        for command in self.__commands:
            vcmds.add(command)

        print("Generating oracle...")
        self.__generate_oracle(vehicle, enable_workaround)
        print("Generated oracle")

        print("Uploading mission...")
        for (i, command) in enumerate(vcmds):
            print("{}: {}".format(i, command))
        vcmds.upload()
        vcmds.wait_ready()
        print("Uploaded mission")

    def __start(self, vehicle):
        message = vehicle.message_factory.command_long_encode(
            0,  # target_system
            0,  # target_component
            300,  # MAV_CMD MISSION_START
            0,  # confirmation
            1,  # param 1 first mission item to run
            len(self) + 1,  # param 2 final mission item to run
            0,  # param 3 (empty)
            0,  # param 4 (empty)
            0,  # param 5 (empty)
            0,  # param 6 (empty)
            4,  # param 7 (empty)
        )
        vehicle.send_mavlink(message)

    def execute(self, time_limit, vehicle, speedup, timeout_heartbeat, check_wps, enable_workaround):
        """
        Executes this mission on a given vehicle.

        Parameters:
            time_limit: the number of seconds that the vehicle should be given
                to finish executing the mission before aborting the mission.
            vehicle: the vehicle that should execute the mission.
            speedup: the speed-up factor used by the simulation.

        Returns:
            a sequence of tuples of the form (wp, state), where wp corresponds
            to a given waypoint in the mission, and state describes the state
            of the vehicle when it reached that waypoint.

        Raises:
            TimeoutError: if the mission doesn't finish executing within the
                given time limit.
        """
        # modify the time limit according to the simulator speed-up
        if speedup > 1:
            time_limit = int((time_limit / speedup) + 10)
            print("using wall-clock time limit: {} seconds".format(time_limit))

        def timeout_handler(signum, frame):
            raise TimeoutError
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(time_limit)

        while not vehicle.is_armable:
            time.sleep(0.2)

        # arm the rover
        vehicle.armed = True
        while not vehicle.armed:
            print("waiting for the vehicle to be armed...")
            time.sleep(0.1)
            vehicle.armed = True

        self.issue(vehicle, enable_workaround)

        # trigger the mission by switching the vehicle's mode to "AUTO"
        vehicle.mode = VehicleMode("AUTO")
        self.__start(vehicle)

        # monitor the mission
        mission_complete = [False]
        actual_num_wps_visited = [0]
        expected_num_wps_visited = self.__expected_num_wps_visited
        is_copter = self.__vehicle_kind == 'ArduCopter'
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
