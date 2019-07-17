#!/usr/bin/env python

from evdev import InputDevice, categorize, ecodes
import sys

if __name__ == '__main__':
    #Store the maximum and minimum value for ecodes to display the range of possible values in joystick controls
    ecodes_min = {}
    ecodes_max = {}
    devpath = sys.argv[1]
    #for dev in [evdev.InputDevice(path) for path in evdev.list_devices()]:
    dev     = InputDevice(devpath)
    print(dev)
    print(dev.capabilities(verbose=True))
    for e in dev.read_loop():
        if (e.type == ecodes.EV_KEY) or (e.type == ecodes.EV_ABS):
            if not e.code in ecodes_max:
                ecodes_max[e.code] = e.value
            else:
                ecodes_max[e.code] = e.value if e.value > ecodes_max[e.code] else ecodes_max[e.code]

            if not e.code in ecodes_min:
                ecodes_min[e.code] = e.value
            else:
                ecodes_min[e.code] = e.value if e.value < ecodes_min[e.code] else ecodes_min[e.code]

            if (e.type == ecodes.EV_KEY):
                ecode_str = ecodes.BTN[e.code]
            else:
                ecode_str = ecodes.ABS[e.code]

            print("Event Code: %s (%d), Value: %d, Min: %d, Max: %d" % (ecode_str, e.code, e.value, ecodes_min[e.code], ecodes_max[e.code]))
