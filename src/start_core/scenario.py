__all__ = ['Scenario']

import os
import logging
import shutil
import tempfile
import subprocess
from contextlib import contextmanager

import attr
import configparser

from .mission import Mission
from .attack import Attack
from .sitl import SITL
from .exceptions import FileNotFoundException, UnsupportedRevisionException

logger = logging.getLogger(__name__)  # type: logging.Logger
logger.setLevel(logging.DEBUG)


SUPPORTED_REVISIONS = [
    '368698d',
    'b5467be',
    '0626d10',
    '73c0905',
    '4e8399c',
    '21abe11',
    '4ab2ff8',
    '2b49a3a',
    'cca9a6e',
    'c99cc46',
    '1e05804',
    '3ee064d',
    'b622fe1'
]

BRANCH_TO_REVISION = {
    'Sept-demo-cca9a6e-April-21': 'cca9a6e',
    'Sept-demo-c99cc46-May-18': 'c99cc46',
    'Sept-demo-b622fe1-June-27': 'b622fe1',
    'Sept-demo-b5467be-Jan-17': 'b5467be',
    'Sept-demo-4e8399c-Feb-19': '4e8399c',
    'Sept-demo-4ab2ff8-March-11': '4ab2ff8',
    'Sept-demo-3ee064d-June-12': '3ee064d',
    'Sept-demo-2b49a3a-April-11': '2b49a3a',
    'Sept-demo-21abe11-March-9': '21abe11',
    'Sept-demo-1e05804-May-25': '1e05804',
    'Sept-demo-0626d10-Jan-29': '0626d10',
    'Sept-demo-368698d-Jan-4': '368698d'
}


@attr.s(frozen=True)
class Scenario(object):
    """
    Provides an immutable description of a START defect scenario.
    """
    filename = attr.ib(type=str)
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
        if revision in BRANCH_TO_REVISION:
            revision = BRANCH_TO_REVISION[revision]
        if revision not in SUPPORTED_REVISIONS:
            msg = "unsupported ArduPilot source code revision: {}"
            msg = msg.format(revision)
            raise UnsupportedRevisionException(msg)

        fn_attack = cfg.get('Attack', 'attack')
        fn_attack = os.path.join(dir_cfg, fn_attack)
        attack = Attack(script=fn_attack,
                        flags=cfg.get('Attack', 'script_flags'),
                        longitude=cfg.getfloat('Attack', 'longitude'),
                        latitude=cfg.getfloat('Attack', 'latitude'),
                        radius=cfg.getfloat('Attack', 'radius'))

        vehicle = cfg.get('General', 'vehicle')
        assert vehicle in ['APMrover2', 'ArduCopter', 'ArduPlane']

        home_lat = cfg.getfloat('Mission', 'latitude')
        assert home_lat >= 0.0 and home_lat <= 90.0
        home_lon = cfg.getfloat('Mission', 'longitude')
        assert home_lon >= -180.0 and home_lon <= 180.0
        home_alt = cfg.getfloat('Mission', 'altitude')
        home_heading = cfg.getfloat('Mission', 'heading')
        assert home_heading >= 0.0 and home_heading <= 360.0
        home = (home_lat, home_lon, home_alt, home_heading)

        fn_mission = cfg.get('Mission', 'mission')
        fn_mission = os.path.join(dir_cfg, fn_mission)
        mission = Mission.from_file(home, vehicle, fn_mission)

        logging.debug("building SITL for scenario")
        name_binary = ({
            'APMrover2': 'ardurover',
            'ArduCopter': 'arducopter',
            'ArduPlane': 'arduplane'
        })[vehicle]
        fn_harness = os.path.join(dir_source, 'Tools/autotest/sim_vehicle.py')
        sitl = SITL(fn_harness, vehicle, home)
        logging.debug("built SITL for scenario: %s", sitl)

        if not os.path.isfile(fn_diff):
            msg = "failed to locate vulnerability file: {}".format(fn_diff)
            raise FileNotFoundException(msg)

        return Scenario(filename=fn,
                        name=cfg.get('General', 'name'),
                        directory=dir_cfg,
                        sitl=sitl,
                        mission=mission,
                        attack=attack,
                        diff_fn=fn_diff,
                        revision=revision)

    @contextmanager
    def build(self, filename_patch=None):
        """
        Copies the source code for this scenario to a temporary directory
        before optionally applying a patch, and building its SITL binary.

        Returns:
            a SITL object that provides access to the binary
        """
        # type: (str) -> SITL
        logger.debug("building scenario: %s", self.name)
        if filename_patch:
            logger.debug("applying patch: %s", filename_patch)

        # FIXME this is a hack that works with our existing scenarios but
        #    relies on the source directory being named "vulnerable_ardupilot".
        dir_original = os.path.join(self.directory, 'vulnerable_ardupilot')

        dir_ctx = tempfile.mkdtemp()
        try:
            logger.debug("using temporary build context: %s", dir_ctx)
            logger.debug("copying files to build context")
            shutil.copytree(dir_original, dir_ctx)
            logger.debug("copied files to build context")

            logger.debug("destroying git index")
            cmd = ' && '.join([
                "rm -rf .git",
                "find . -name .git -delete",
                "git init",
                "git add waf",
                "git commit -m 'borked'",
            ])
            subprocess.check_call(cmd, cwd=dir_ctx)
            logger.debug("destroyed git index")

            if filename_patch:
                logger.debug("applying patch")
                cmd = "patch -p0 -i '{}'".format(filename_patch)
                subprocess.check_call(cmd, cwd=dir_ctx)
                logger.debug("applied patch")

            logger.debug("building binary")
            cmd = ({
                'APMrover2': 'rover',
                'ArduCopter': 'copter',
                'ArduPlane': 'arduplane'
            })[self.mission.vehicle]
            cmd = ' && '.join([
                "./waf configure --no-submodule-update",
                "./waf {}".format(cmd)
            ])
            subprocess.check_call(cmd, shell=True, cwd=dir_ctx)
            logger.debug("built binary")

            fn_harness = os.path.join(dir_ctx, 'Tools/autotest/sim_vehicle.py')
            sitl = SITL(fn_harness, self.mission.vehicle, self.mission.home)
            yield sitl
        finally:
            logger.debug("destroying temporary build context: %s", dir_ctx)
            shutil.rmtree(dir_ctx, ignore_errors=True)
            logger.debug("destroyed temporary build context: %s", dir_ctx)
