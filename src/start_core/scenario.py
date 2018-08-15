import os

import attr
import configparser

from .mission import Mission
from .attack import Attack
from .sitl import SITL
from .exceptions import FileNotFoundException, UnsupportedRevisionException

__all__ = ['Scenario']

SUPPORTED_REVISIONS = [
    '368698d',
    'b5467be',
    '0626d10',
    '73c0905',
    '4e8399c',
    '21abe11',
    '4ab2ff81',
    '2b49a3a1',
    'cca9a6e1',
    'c99cc46',
    '1e05804',
    '3ee064d',
    'b622fe1'
]


@attr.s(frozen=True)
class Scenario(object):
    """
    Provides an immutable description of a START defect scenario.
    """
    name = attr.ib(type=str)
    directory = attr.ib(type=str)
    sitl = attr.ib(type=SITL)
    mission = attr.ib(type=Mission)
    attack = attr.ib(type=Attack)
    revision = attr.ib(type=str)
    diff_fn = attr.ib(type=str)

    @staticmethod
    def from_file(fn  # type: str
                  ):  # type: Scenario
        """
        Constructs a description of a scenario from a given file.
        """
        if not os.path.isfile(fn):
            msg = "failed to read configuration file: {}".format(fn)
            raise FileNotFoundException(msg)

        cfg = configparser.SafeConfigParser()
        fn_cfg = os.path.join(os.path.dirname(__file__),
                              'config/scenario.default.config')
        cfg.read(fn_cfg)
        cfg.read(fn)
        return Scenario.from_config(fn, cfg)

    @staticmethod
    def from_config(fn,  # type: str
                    cfg  # type: configparser.SafeConfigParser
                    ):  # type: Scenario
        """
        Constructs a scenario description from a parsed configuration read from
        a given file.
        """
        dir_cfg = os.path.dirname(fn)
        dir_source = os.path.join(dir_cfg, cfg.get("General", "ardupilot"))
        fn_mission = os.path.join(dir_cfg, cfg.get("Mission", "mission"))
        fn_diff = os.path.join(dir_cfg, cfg.get("General", "vulnerability"))

        revision = cfg.get("General", "revision")
        if revision not in SUPPORTED_REVISIONS:
            msg = "unsupported ArduPilot source code revision: {}"
            msg = msg.format(revision)
            raise UnsupportedRevisionException(msg)

        attack = Attack(script='attack.py',  # FIXME
                        flags=cfg.get('Attack', 'script_flags'),
                        longitude=cfg.getfloat('Attack', 'longitude'),
                        latitude=cfg.getfloat('Attack', 'latitude'),
                        radius=cfg.getfloat('Attack', 'radius'))

        mission = Mission.from_file(sitl.home,
                                    sitl.vehicle,
                                    fn_mission)

        logging.debug("building SITL for scenario")
        name_binary = ({
            'APMrover2': 'ardurover',
            'ArduCopter': 'arducopter',
            'ArduPlane': 'arduplane'
        })[scenario.mission.vehicle]
        fn_harness = os.path.join(dir_source, 'Tools/autotest/sim_vehicle.py')
        sitl = SITL(fn_harness, mission.vehicle, mission.home)
        logging.debug("built SITL for scenario: %s", sitl)

        if not os.path.isfile(fn_diff):
            msg = "failed to locate vulnerability file: {}".format(fn_diff)
            raise FileNotFoundException(msg)

        return Scenario(name=cfg.get('General', 'name'),
                        directory=dir_cfg,
                        sitl=sitl,
                        mission=mission,
                        attack=attack,
                        diff_fn=fn_diff,
                        revision=revision)
