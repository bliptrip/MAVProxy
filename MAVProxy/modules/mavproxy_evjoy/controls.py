'''EvJoy control classes'''
import evdev
from evdev import ecodes
from MAVProxy.modules.lib import mp_util
from MAVProxy.mavproxy import run_script
import os

def scale(val,
          inlow=-1, inhigh=1,
          outlow=1000, outhigh=2000):
    '''Scale an in value in the range (inlow, inhigh) to the
    range (outlow, outhigh).'''
    return (
        ((float(val) - inlow) / (inhigh - inlow)) *
        (outhigh - outlow) + outlow
    )


class Control (object):
    '''Base class for all controls'''
    def __init__(self, state,
                 invert=False, inlow=0, inhigh=1,
                 outlow=1000, outhigh=2000):
        self.state = state
        self.inlow = inlow
        self.inhigh = inhigh
        if( invert ):
            self.outlow = outhigh
            self.outhigh = outlow
        else:
            self.outlow = outlow
            self.outhigh = outhigh

    #Default is_active() will return False.  For some controls, an 'active' state doesn't make sense
    def is_active(self):
        return False


class Button (Control):
    '''A Button acts like a momentary switch.  When pressed, the
    corresponding channel value is set to `outhigh`; when released,
    the value is set to `outlow`.'''

    def __init__(self, state, id, **kwargs):
        super(Button, self).__init__(state, **kwargs)
        self.id = id
        self.ecode = ecodes.ecodes[id]
        self.state[self.ecode] = self.inlow
        
    def is_active(self):
        return(self.state[self.ecode])

    @property
    def value(self):
        pressed = self.is_active()
        if pressed :
            return self.outhigh
        else:
            return self.outlow


class ComboButton (Control):
    '''A ComboButton is equivalent to an AND logic gate after two or
    more buttons.  All buttons listed must be pressed simultaneously
    to set the output of the channel to highoutput.'''

    def __init__(self, state, cbuttons, **kwargs):
        super(ComboButton, self).__init__(state, **kwargs)
        for button in cbuttons:
            button['ecode'] = ecodes.ecodes[button['id']]
            self.state[button['ecode']] = 0
        self.cbuttons = cbuttons

    def is_active(self):
        all_active = True
        for button in self.cbuttons:
            pressed = self.state[button['ecode']]
            if not pressed:
                all_active = False
                break
        return(all_active)


    @property
    def value(self):
        all_pressed = self.is_active()
        if all_pressed:
            val = self.outhigh
        else:
            val = self.outlow
        return val


class MultiButton (Control):
    '''A MultiButton maps multiple buttons to the same channel like a
    multiple-position switch.  When a button is pressed, the channel
    is set to the corresponding value.  When a button is released, no
    changes is made to the channel.'''

    def __init__(self, state, buttons, **kwargs):
        super(MultiButton, self).__init__(state, **kwargs)
        for button in buttons:
            button['ecode'] = ecodes.ecodes[button['id']]
            self.state[button['ecode']] = 0
        self.buttons = buttons
        self._value = buttons[0]['value']

    @property
    def value(self):
        for button in self.buttons:
            pressed = self.state[button['ecode']]
            if pressed:
                self._value = button['value']
                break
        return self._value


class Axis (Control):
    '''An Axis maps a evjoy axis to a channel.  Set `invert` to
    `True` in order to reverse the direction of the input.'''

    def __init__(self, state, id, **kwargs):
        super(Axis, self).__init__(state, **kwargs)
        self.id = id
        self.ecode = ecodes.ecodes[self.id]
        self.state[self.ecode] = self.inlow

    @property
    def value(self):
        val = self.state[self.ecode]
        return scale(val, inlow=self.inlow, inhigh=self.inhigh, outlow=self.outlow, outhigh=self.outhigh)


class Hat (Control):
    '''A Hat maps one axis of a hat as if it were a toggle switch.
    When the axis goes negative, the corresponding channel value is
    set to `outputlow`.  When the axis goes positive, the value is set
    to `outputhigh`.  No change is made when the axis returns to 0.'''

    def __init__(self, state, id, **kwargs):
        super(Hat, self).__init__(state, **kwargs)
        self.id = id
        self.ecode = ecodes.ecodes[self.id]
        self.state[self.ecode] = self.inlow
        self._value = self.outlow

    @property
    def value(self):
        val = self.state[self.ecode]
        if val != 0:
            self._value = scale(val,
                                outlow=self.outlow, outhigh=self.outhigh)
        return self._value


class EvJoy (object):
    '''A EvJoy manages a collection of Controls.'''

    def __init__(self, evjoy, controls, search):
        self.evjoy = evjoy
        self.state = {}
        self.controls = controls

        self.search = search

        self.chan_max = max(control['channel']
                            for control in controls['controls'] if 'channel' in control)
        self.channels = [None] * self.chan_max
        self.actions  = []

        for control in controls['controls']:
            if control['type'] == 'button':
                kwargs = {k: control[k]
                          for k in control.keys()
                          if k in ['invert', 'outlow', 'outhigh']}
                handler = Button(self.state, control['id'], **kwargs)

            elif control['type'] == 'axis':
                kwargs = {k: control[k]
                          for k in control.keys()
                          if k in ['inlow', 'inhigh',
                                   'outlow', 'outhigh', 'invert']}
                handler = Axis(self.state, control['id'], **kwargs)

            elif control['type'] == 'multibutton':
                handler = MultiButton(self.state,
                                   buttons=control['buttons'])

            elif control['type'] == 'combobutton':
                handler = ComboButton(self.state,
                                   cbuttons=control['cbuttons'])

            elif control['type'] == 'hat':
                kwargs = {k: control[k]
                          for k in control.keys()
                          if k in ['invert', 'outlow', 'outhigh']}
                handler = Hat(self.state, control['id'], **kwargs)

            if 'channel' in control:
                self.channels[control['channel']-1] = handler

            if 'action' in control:
                self.actions.append({'handler': handler, 'action': self.find_script(control['action'])})

        #Assume all start out initially inactive
        self.active = [0] * len(self.actions)

        #Read in initial values
        #Set active buttons
        for ak in self.evjoy.active_keys():
            if ak in self.state:
                self.state[ak] = 1
        caps = self.evjoy.capabilities(absinfo=True) 
        #Process Axis and HAT data
        absinfos = caps[ecodes.EV_ABS]
        for absinfo in absinfos:
            k = absinfo[0]
            if k in self.state:
                self.state[k] = absinfo[1].value

    def find_script(self, script):
        full_path = None
        for p in self.search:
            full_path = os.path.join(p, script)
            if os.path.exists(full_path):
                break
            full_path = os.path.join(p, 'scripts', script)
            if os.path.exists(full_path):
                break
        return(full_path)

    
    def read(self):
        '''Returns an array of channel values.  Return 0 for channels
        not specified in the control definition.'''

        try:
            for e in self.evjoy.read():
                if e.code in self.state:
                    print("Setting %d to %d." % (e.code, e.value))
                    self.state[e.code] = e.value
        except Exception as e:
            pass

        values = [int(handler.value) if handler is not None else 0 for handler in self.channels]

        return(values)

    def act(self):
        '''For any active controls that are active and have changed state since last time, execute user scripts associated
        with controls.'''
        #Figure out with ones are currently active
        active = [action['handler'].is_active() for action in self.actions]
        active = [1 if a else 0 for a in active] #Convert to 0's and 1's as this helps with difference logic below -- only want to execute action on state change
        for i in range(0,len(active)):
            d = active[i] - self.active[i]
            if d > 0 and self.actions[i]['action'] is not None: #Execute action
                run_script(self.actions[i]['action'])
        self.active = active
