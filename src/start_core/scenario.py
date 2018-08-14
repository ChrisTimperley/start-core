import os

import attr
import configparser

from .mission import Mission
from .attack import Attack
from .sitl import SITL

__all__ = ['Scenario']


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

    @staticmethod
    def from_file(fn  # type: str
                  ):  # type: Scenario
        """
        Constructs a description of a scenario from a given file.
        """
        if not os.path.isfile(fn):
            msg = "failed to read confiugration file: {}".format(fn)
            raise FileNotFoundError(msg)

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

        attack = Attack(script='attack.py',  # FIXME
                        flags=cfg.get('Attack', 'script_flags'),
                        longitude=cfg.getfloat('Attack', 'longitude'),
                        latitude=cfg.getfloat('Attack', 'latitude'),
                        radius=cfg.getfloat('Attack', 'radius'))
        sitl = SITL.from_cfg(cfg, dir_source)
        mission = Mission.from_file(sitl.home_location,
                                    sitl.vehicle_kind,
                                    timeout,
                                    fn_mission)
        return Scenario(name=cfg.get('General', 'name'),
                        directory=dir_cfg,
                        sitl=sitl,
                        mission=mission,
                        attack=attack)
