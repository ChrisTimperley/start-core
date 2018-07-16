# This script is responsible for launching and closing the SITL.
import subprocess
import os
import signal
import configparser


try:
    DEVNULL = subprocess.DEVNULL
except AttributeError:
    DEVNULL = open(os.devnull, 'w')


class SITL(object):
    @staticmethod
    def from_cfg(cfg, dir_source, home = None, vehicle = None):
        if not vehicle:
            vehicle = cfg.get("General", "vehicle")
        if not home:
            lat = cfg.getfloat("Mission", "latitude")
            lon = cfg.getfloat("Mission", "longitude")
            alt = cfg.getfloat("Mission", "altitude")
            heading = cfg.getfloat("Mission", "heading")
            home = (lat, lon, alt, heading)

        assert isinstance(home, tuple)
        assert len(home) == 4
        assert all(isinstance(x, float) for x in home)
        assert vehicle in ['APMrover2', 'ArduCopter', 'ArduPlane']

        return SITL(vehicle=vehicle,
                    home=home,
                    dir_source=dir_source)

    def __init__(self,
                 vehicle,
                 home,
                 dir_source):
        binary_name = ({
            'APMrover2': 'ardurover',
            'ArduCopter': 'arducopter',
            'ArduPlane': 'arduplane'
        })[vehicle]

        self.__dir_base = dir_source
        self.__vehicle = vehicle
        self.__process = None
        self.__home_loc = home
        self.__path_binary = os.path.join(self.__dir_base, 'build/sitl/bin', binary_name)

        assert os.path.exists(self.__path_binary), \
            "binary does not exist: {}".format(self.__path_binary)

    @property
    def vehicle(self):
        """
        The name of the vehicle under test.
        """
        return self.__vehicle

    @property
    def home(self):
        """
        The initial home location of the vehicle.
        """
        return self.__home_loc

    def command(self, prefix = None, speedup = 1):
        if prefix is None:
            prefix = ''

        script_sim = os.path.join(self.__dir_base, 'Tools/autotest/sim_vehicle.py')
        cmd = [
            script_sim,
            "--mavproxy-args '--daemon --out 127.0.0.1:14552 --out 127.0.0.1:14553'", # don't attach to STDIN!
            "-l", "{},{},{},{}".format(*self.__home_loc),
            "-v", self.__vehicle,
            "-w",
            "--speedup={}".format(speedup),
            "--no-rebuild "
            # "--ardu-dir ", self.__dir_base, # BAD: no longer supported
            # "--ardu-binary", self.__path_binary # BAD: no longer supported
        ]
        return prefix + ' '.join(cmd)

    def start(self, prefix = None, speedup = 1):
        command = self.command(prefix=prefix, speedup=speedup)
        print(command)
        self.__process = subprocess.Popen(command,
                                          shell=True,
                                          stdin=DEVNULL,
                                          stdout=DEVNULL,
                                          stderr=DEVNULL,
                                          preexec_fn=os.setsid)

    def stop(self):
        if self.__process:
            os.killpg(self.__process.pid, signal.SIGTERM)
        self.__process = None


if __name__ == '__main__':
    cfg = configparser.SafeConfigParser()
    assert os.path.isfile('/experiment/config/scenario.cfg'), \
        "cfg file does not exist"

    cfg.read('/experiment/config/scenario.cfg')
    sitl = SITL.from_cfg(cfg)
    print(sitl.command)
