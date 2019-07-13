from __future__ import print_function

import evdev
import os
import pkg_resources
import yaml
import fnmatch

from MAVProxy.modules.lib import mp_module
from MAVProxy.modules.lib import mp_util
from MAVProxy.modules.lib import mp_settings

from MAVProxy.modules.mavproxy_evjoy import controls


class EvJoy(mp_module.MPModule):
    '''
    evjoy status
    evjoy probe
    '''

    def __init__(self, mpstate):
        """Initialise module"""
        super(EvJoy, self).__init__(mpstate, 'evjoy',
                                       'A flexible evjoy driver without the pygame baggage.')

        self.evjoy = None

        self.init_settings()
        self.init_commands()

        self.probe()

    def log(self, msg, level=0):
        if self.mpstate.settings.moddebug < level:
            return

        print('{}: {}'.format(__name__, msg))

    def init_settings(self):
        pass

    def init_commands(self):
        self.log('Initializing commands', 2)
        self.add_command('evjoy', self.cmd_evjoy,
                         "A flexible evjoy driver without the pygame baggage.",
                         ['status',  'probe'])

    def load_definitions(self):
        self.log('Loading evjoy definitions', 1)

        self.joydefs = []
        search = []

        userevjoys = os.environ.get(
            'MAVPROXY_EVJOY_DIR',
            mp_util.dot_mavproxy('evjoy'))
        if userevjoys is not None and os.path.isdir(userevjoys):
            search.append(userevjoys)

        search.append(pkg_resources.resource_filename(__name__, 'joysticks'))

        for path in search:
            self.log('Looking for evjoy definitions in {}'.format(path),
                     2)
            path = os.path.expanduser(path)
            for dirpath, dirnames, filenames in os.walk(path):
                for joyfile in filenames:
                    root, ext = os.path.splitext(joyfile)
                    if ext[1:] not in ['yml', 'yaml', 'json']:
                        continue

                    joypath = os.path.join(dirpath, joyfile)
                    self.log('Loading definition from {}'.format(joypath), 2)
                    with open(joypath, 'r') as fd:
                        joydef = yaml.safe_load(fd)
                        joydef['path'] = joypath
                        self.joydefs.append(joydef)

    def probe(self):
        self.load_definitions()

        for dev in [evdev.InputDevice(path) for path in evdev.list_devices()]:
            self.log("Found evjoy (%s)" % (dev.name))
            for joydef in self.joydefs:
                if 'match' not in joydef:
                    self.log('{} has no match patterns, ignoring.'.format(
                        joydef['path']), 0)
                    continue
                for pattern in joydef['match']:
                    if fnmatch.fnmatch(dev.name.lower(),
                                       pattern.lower()):
                        self.log('Using {} ("{}" matches pattern "{}")'.format(
                            joydef['path'], dev.name, pattern))
                        self.evjoy = controls.EvJoy(dev, joydef)
                        return

        print('{}: Failed to find matching evjoy.'.format(__name__))

    def usage(self):
        '''show help on command line options'''
        return "Usage: evjoy <status|probe|set>"

    def cmd_evjoy(self, args):
        if not len(args):
            self.log('No subcommand specified.')
        elif args[0] == 'status':
            self.cmd_status()
        elif args[0] == 'probe':
            self.cmd_probe()
        elif args[0] == 'help':
            self.cmd_help()

    def cmd_help(self):
        print('evjoy probe -- reload and match evjoy definitions')
        print('evjoy status -- show currently loaded definition, if any')

    def cmd_probe(self):
        self.log('Re-detecting available evjoys', 0)
        self.probe()

    def cmd_status(self):
        if self.evjoy is None:
            print('No active evjoy')
        else:
            print('Active evjoy:')
            print('Path: {path}'.format(**self.evjoy.controls))
            print('Description: {description}'.format(
                **self.evjoy.controls))

    def idle_task(self):
        if self.evjoy is None:
            return

        override = self.module('rc').override[:]
        values = self.evjoy.read()
        override = values + override[len(values):]

        if override != self.module('rc').override:
            self.log('EvJoy Override mismatch:', level=3)
            print(override)
            self.module('rc').override = override
            self.module('rc').override_period.force()


def init(mpstate):
    '''initialise module'''
    return EvJoy(mpstate)
