import argparse
import sys

from .test import TestCase

def run_test(test,
             sitl_prefix = None,
             speedup = 1,
             time_limit = 240,
             liveness_timeout = 1,
             check_wps = False,
             enable_workaround = True):
    assert speedup > 0, "expected positive speed-up factor"

    (status, msg) = test.execute(sitl_prefix=sitl_prefix,
                                 speedup=speedup,
                                 time_limit=time_limit,
                                 liveness_timeout=liveness_timeout,
                                 check_wps=check_wps,
                                 enable_workaround=True)
    if status:
        print("PASSED")
    else:
        print("FAILED: {}".format(msg))
        sys.exit(1)


def cli_execute(args):
    test = TestCase(args.mission,
                    dir_source=args.source_dir,
                    fn_cfg_scenario=args.config,
                    fn_cfg_default=args.config_default,
                    connection_timeout=args.connection_timeout,
                    use_attacker=args.attack)
    run_test(test,
             sitl_prefix=args.sitl_prefix,
             speedup=args.speedup,
             time_limit=args.time_limit,
             liveness_timeout=args.liveness_timeout,
             check_wps=args.check_wps,
             enable_workaround=(not args.no_workaround))


def cli_test(args):
    # (home_lat, home_lon, home_alt, home_heading)
    # FIXME use missions in the data directory?
    test_suite = {
        'p1':
            TestCase('/experiment/mission.txt'),
        'n1':
            TestCase('/experiment/mission.txt',
                     use_attacker=True)
    }

    if args.id not in test_suite:
        print("Unrecognised test identifier provided.")
        sys.exit(2)

    run_test(test_suite[args.id],
             speedup=args.speedup,
             time_limit=args.time_limit,
             liveness_timeout=args.liveness_timeout,
             check_wps=args.check_wps,
             enable_workaround=(not args.no_workaround))


def main():
    # construct the test suite
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()

    # execute a provided test
    g_execute = subparsers.add_parser('execute',
                                      help='executes a given mission file for the system under test')
    g_execute.add_argument('mission',
                           help='the absolute path to the mission file for the mission that should be executed.',
                           type=str)
    g_execute.add_argument('--sitl-prefix',
                           type=str,
                           help='a prefix that should be prepended to the command used to launch the SITL.',
                           default='')
    g_execute.add_argument('--attack',
                           help='used to enable or disable the attack. (NOT SUPPORTED OUTSIDE OF DOCKER CONTAINER.)',
                           action='store_true')
    g_execute.add_argument('--source-dir',
                           type=str,
                           default='/experiment/source',
                           help='the absolute path to the ArduPilot source directory for the system under test.')
    g_execute.add_argument('--connection-timeout',
                           type=int,
                           default=5,
                           help='the timeout period when connecting to the simulator')
    g_execute.add_argument('--config',
                           type=str,
                           default='/experiment/config/scenario.cfg',
                           help='the absolute path to the configuration file for the scenario that describes the system under test.')
    g_execute.add_argument('--config-default',
                           type=str,
                           default='/experiment/config/default.cfg',
                           help='the absolute path to the default configuration file used by START.')
    g_execute.add_argument('--speedup',
                           default=1,
                           type=int,
                           help='speed-up factor to use in simulation'
                           )
    g_execute.add_argument('--time-limit',
                           type=int,
                           default=240,
                           help='the time limit for the mission execution.')
    g_execute.add_argument('--liveness-timeout',
                           type=int,
                           default=1,
                           help='if the vehicle is unresponsive for this period or longer.')
    g_execute.add_argument('--check-wps',
                           action='store_true',
                           help='enables checking of number of visited WPs')
    g_execute.add_argument('--no-workaround',
                           action='store_true',
                           help='disables a workaround that causes the oracle to ignore all commands beyond a known non-terminating command.')
    g_execute.set_defaults(func=cli_execute)

    # execute a prespecified test
    g_test = subparsers.add_parser('test',
                                   help='executes a prespecified test supplied by this test harness.')
    g_test.add_argument('id',
                        help='the unique identifier for the test.',
                        type=str)
    g_test.add_argument('--speedup',
                        default=1,
                        type=int,
                        help='speed-up factor to use in simulation')
    g_test.add_argument('--time-limit',
                        type=int,
                        default=240,
                        help='the time limit for the test execution.')
    g_test.add_argument('--check-wps',
                        action='store_true',
                        help='enables checking of number of visited WPs')
    g_test.add_argument('--liveness-timeout',
                        type=int,
                        default=3,
                        help='if the vehicle is unresponsive for this period or longer.')
    g_test.add_argument('--no-workaround',
                        action='store_true',
                        help='disables a workaround that causes the oracle to ignore all commands beyond a known non-terminating command.')
    g_test.set_defaults(func=cli_test)

    args = parser.parse_args()
    if 'func' in vars(args):
        args.func(args)