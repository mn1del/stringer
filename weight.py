#!/usr/bin/env python3


import sys
import os
import time
import RPi.GPIO as GPIO

sys.path.append(os.path.abspath(os.path.join("..")))
from rpigpio import HX711
from rpigpio import LCD1602
from rpigpio import RotaryEncoder
from rpigpio import Toggle
from rpigpio import Button
from rpigpio import Stepper

import config  # where calibration settings etc are stored

class Stringer():
    def __init__(self):
        """
        Hardware and behaviour of the stringer. 
        """
        # setup hardware
        GPIO.setmode(GPIO.BCM)
        self.n_obs = 5
        self.target_kgs = 20.0
        self.movement_mm = 0.25  # distance to increment the leadscrew
        self.limit_backoff_mm = 10  # distance to back off the limit switch when triggered
        self.leadscrew_lead = 2
        self.steps_per_rev = 400
        self.hx = HX711(data=27, clock=17, channel="A", gain=128, printout=False)
        self.lcd = LCD1602(data_pins=[6,13,19,26], rs_pin=11, e_pin=5)
        self.rot = RotaryEncoder(
                clk=18,
                dt=15,
                button=14,
                counter=self.target_kgs*10,
                long_press_secs=1.0,
                debounce_n=2)
        self.button = self.rot.BUTTON_LAST_PRESS
        # set up normally closed limit switches (allows both switches to share a circuit)
        self.limit_switch = Button(button_pin=12, pull_up=True, debounce_delay_secs=0.01)  
        self.stepper = Stepper(
                dir_pin=8, 
                step_pin=7, 
                sleep_pin=25,
                ms0_pin=21, 
                ms1_pin=20, 
                ms2_pin=16,
                steps_per_rev=self.steps_per_rev,
                microstep_mode=2,
                driver="drv8825")

        # Attempt to read in calibration factors and set mode accordingly
        try:
            ### ************* Logic to check existence of calibration factors here ****************
            self.cal_factor = config.cal_factor
            self.cal_offset = config.cal_offset
        except:
            self.cal_factor = None
            self.cal_offset = None
            print("Some sort of problem reading in calibration factors")
            
        # define any state variables
        if (self.cal_factor==None) | (self.cal_offset==None):
            self.MODE = "calibrating"
        else:
            self.MODE = "resting"
            
    def start(self):
        """
        Start the logic loop
        """
        try:
            # go to the home location of the tensioner
            self.go_home() 
            while True:
                if self.MODE == "resting":
                    self.rest()
                elif self.MODE == "tensioning":
                    self.tension()
                elif self.MODE == "calibrating":
                    self.calibrate
                else:
                    print("Unknown mode!")
        except:
            # code to cleanup here
            print("Something went wrong in the master loop")
            pass
        finally:
            self.stepper.sleep()
            self.lcd.cleanup()
            self.hx.cleanup()
            GPIO.cleanup()
                   
    def rest(self):
        """
        HOMEs the tensioner, SLEEPs the stepper, and allows target_kgs to be changed
        with the rotary encoder. Then just awaits a button press to either start
        tensioning or calibrating
        """
        # initialize rot.COUNTER
        self.rot.COUNTER = self.target_kgs * 10
        # HOME the tensioner if necessary
        if not self.HOME:
            self.go_home()
        # put the stepper to sleep
        self.stepper.sleep()
        
        # start loop
        while self.MODE == "resting":
            # control target_kgs with the rotary encoder
            self.target_kgs = self.rot.COUNTER/10
            # display target_kgs
            self.lcd.lcd_string("Target: {:,.1f} kgs".format(self.target_kgs), self.lcd.LCD_LINE_1)
            self.lcd.lcd_string("press to tension", self.lcd.LCD_LINE_2)
            # check for change in MODE
            if self.rot.BUTTON_LAST_PRESS != self.button:
                if self.rot.BUTTON_LONG_PRESS:
                    self.MODE = "calibrating"
                else:
                    self.MODE = "tensioning"
        
    def tension(self):
        """
        Initialize rotary encoder counter with target_kgs and start tensioning logic loop.
        target_kgs can be dynamically managed with the rotary encoder.
        """
        print("In tensioning mode\ntarget_kgs: {}".format(self.target_kgs))
        self.rot.COUNTER = self.target_kgs*10
        
        while self.MODE == "tensioning":
            self.current_kgs = self.raw_to_kgs(self.hx.get_reading(n_obs=5, clip=True))
            self.target_kgs = max(0,min(500, self.rot.COUNTER))/10
            self.lcd.lcd_string("Target: {:,.1f} kg".format(self.target_kgs), self.lcd.LCD_LINE_1)
            self.lcd.lcd_string("Actual: {:,.1f} kg".format(self.current_kgs), self.lcd.LCD_LINE_2)

            if not self.limit_switch_triggered(self.limit_switch):
                if self.current_kgs < self.target_kgs:
                    self.increment_stepper(1, self.movement_mm)
                elif self.current_kgs > self.target_kgs:
                    self.increment_stepper(-1, self.movement_mm)
            else:  # limit hit       
                self.lcd.lcd_string("**** Error ****", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string("** Limit Hit **", self.lcd.LCD_LINE_2)
                self.go_home(far_limit_back_off_mm=self.limit_backoff_mm)
                self.MODE = "resting"
            if self.rot.BUTTON_LAST_PRESS != self.button:
                if self.rot.BUTTON_LONG_PRESS:
                    # The stepper remains energized in the current position
                    self.MODE = "calibrating"
                else:
                    self.go_home()
                    self.MODE = "resting"

    def calibrate(self):
        """
        Step 0: Use the rotary encoder to directly control tension, using a tension/weight of a 
                known value. Press when done.
        Step 1: Enter Known weight and press        
        Step 2: go_home(), message to remove weight and press.
        Step 3: calculate and save calibration factors. Update instance variables. 
        Step 4: Set MODE to "resting"
        """
        calibration_step = 0  # Step 0 requires a known weight
        counter = self.rot.COUNTER  # get initial rotary encoder COUNTER value
        cal_readings = []  # to be populated with len==2 list of [known_weight, raw_reading] 
        
        while self.MODE == "calibrating":
            while calibration_step == 0:  # Control tension directly
                self.lcd.lcd_string("turn to tension", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string("and press", self.lcd.LCD_LINE_2)
                if not self.limit_switch_triggered(self.limit_switch):
                    if self.rot.COUNTER < counter:
                        direction = -1
                        self.increment_stepper(direction, self.movement_mm)
                    elif self.rot.COUNTER > counter:
                        direction = 1
                        self.increment_stepper(direction, self.movement_mm)
                else:  # limit hit       
                    self.lcd.lcd_string("**** Error ****", self.lcd.LCD_LINE_1)
                    self.lcd.lcd_string("** Limit Hit **", self.lcd.LCD_LINE_2)
                    if direction == 1:
                        # implies the far limit was hit
                        far_backoff = self.limit_backoff_mm
                    else:
                        # implies near limit hit, therefore no need to back off
                        far_backoff = 0
                    self.go_home(far_limit_back_off_mm=far_backoff)
                    self.MODE = "resting"
                    if self.rot.BUTTON_LAST_PRESS != self.button:
                        calibration_step = 1
            while calibration_step == 1:
                self.rot.COUNTER = 200  # 20 kgs starting default
                self.lcd.lcd_string("known tension:", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string(
                    "{:,.1f} kgs".format(max(0,min(500, self.rot.COUNTER))/10), 
                    self.lcd.LCD_LINE_2)
                if self.rot.BUTTON_LAST_PRESS != self.button:
                        known_weight = max(0,min(500, self.rot.COUNTER))/10
                        cal_readings.append([known_weight, self.hx.get_reading(n_obs=9, clip=True)])
                        calibration_step = 2
            while calibration_step == 2:
                self.lcd.lcd_string("press when", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string("tension is zero", self.lcd.LCD_LINE_2)
                self.go_home(suppress_message=True)
                if self.rot.BUTTON_LAST_PRESS != self.button:
                        known_weight = 0
                        cal_readings.append([known_weight, self.hx.get_reading(n_obs=9, clip=True)])
                        calibration_step = 3

            # now that we have two calibration readings:
            self.cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
                    / (cal_readings[1][0] - cal_readings[0][0])
            self.cal_offset = cal_readings[1][1] - cal_factor * cal_readings[1][0]
            # store new calibration variables in config.py
            with open("config.py", "w") as f:
                f.write("cal_factor={}\ncal_offset={}".format(self.cal_factor, self.cal_offset))
            self.MODE = "resting"    
        
    def go_home(self, far_limit_back_off_mm=0, suppress_message=False):
        """
        Returns the tensioner to its home position, using the limit switch as a guide.
        Sets HOME state.
        
        args:
            far_limit_back_off_mm: (float) mm to back off the far limit switch first.
                                   Default zero results in no initial far limit backoff
            suppress_message: (bool) If True, do not display "RETURNING HOME" status                        
        """
        # initial back off from far limit switch:
        self.increment_stepper(direction=-1, movement_mm=far_limit_back_off_mm, mm_per_sec=10)
        # Display status
        if not suppress_message:
            self.lcd.lcd_string("***RETURNING***", self.lcd.LCD_LINE_1)
            self.lcd.lcd_string("*****HOME******", self.lcd.LCD_LINE_2)
        # increment backwards until near limit triggered:
        while not self.limit_switch_triggered(self.limit_switch):
            self.increment_stepper(direction=-1, movement_mm=0.5, mm_per_sec=10)
        # finally back off near limit switch     
        self.increment_stepper(direction=1, movement_mm=self.limit_backoff_mm, mm_per_sec=10)
        # set HOME state
        self.HOME = True
        
    def raw_to_kgs(self, raw):
        """
        converts the raw HX711 reading to kgs
        
        args:
            raw: raw HX711 reading
        """
        kgs = max(0,round((raw - cal_offset) / cal_factor,2))
        return kgs
    
    def increment_stepper(self, direction, movement_mm=None, mm_per_sec=10):
        """
        Helper function to increment the leadscrew forwards.
        Sets HOME to False, to register that the position has changed.
        
        args:
        direction: (int) 1 or -1. 1 for tightening motion. -1 for loosening
        movement_mm: (float) movement in mm to increment the leadscrew. 
                     Defaults to self.movement_mm
        mm_per_sec: (int) determines inter step pause length             
        """
        pause_len = 0.5/(self.steps_per_rev * mm_per_sec/self.leadscrew_lead)
        if movement_mm is None:
            movement_mm = self.movement_mm
        direction = int((direction + 1) / 2)  # convert to 0|1   
        n_steps = int(self.steps_per_rev * movement_mm / self.leadscrew_lead)
        self.stepper.step(
                n_steps=n_steps,
                direction=direction,
                inter_step_pause=pause_len,
                high_pause=pause_len)
        self.HOME = False
        
    def limit_switch_triggered(self, limit_switch):
        """
        Returns boolean indicating whether limit switch has been triggered.
        Logic is consistent with a normally closed switch with internal pullup.
        i.e. Trigger => logic LOW
        
        args:
            limit_switch: Button object instance
        """
        if limit_switch.STATE:
            # Normally closed loop has been broken by limit switch trigger. 
            # Therefore internall pull-up pulls the pin HIGH
            triggered = True
        else:
            # Unbroken normally closed loop pulling the pin to ground (i.e. LOW)
            triggered = False
        return triggered          
        
if __name__ == "__main__":
    stringer = Stringer()
    stringer.start()
    
#     try:
#         GPIO.setmode(GPIO.BCM)
#         n_obs = 5
#         target_kgs = 23.0
#         movement_mm = 0.25  # distance to increment the leadscrew
#         leadscrew_lead = 2
#         hx = HX711(data=3, clock=2, channel="A", gain=128, printout=False)
#         lcd = LCD1602(data_pins=[6,13,19,26], rs_pin=11, e_pin=5)
#         rot = RotaryEncoder(clk=7, dt=8, button=25,
#                 counter=target_kgs*10, long_press_secs=1.0, debounce_n=2)
#         button = rot.BUTTON_LAST_PRESS
#         tensioning_mode = False
#         limit_switch = Button(button_pin=15, pull_up=True, debounce_delay_secs=0.01)
#         stepper = Stepper(
#                 dir_pin=8, 
#                 step_pin=7, 
#                 sleep_pin=25,
#                 ms1_pin=21, 
#                 ms2_pin=20, 
#                 ms3_pin=16,
#                 steps_per_rev=200,
#                 microstep_mode=2,
#                 driver="drv8825")
#         # default calibration settings
#         calibrating_mode = False
#         cal_factor = config.cal_factor
#         cal_offset = config.cal_offset
#         while True:
#             """
#             Get reading in kgs, and target kgs
#             """
#             reading = hx.get_reading(n_obs=5, clip=True)
#             converted_reading = max(
#                     0,round((reading - cal_offset) / cal_factor,2))
#             target_kgs = max(0, min(500, rot_COUNTER))/10
#             if tensioning_mode:
#                 if rot.BUTTON_LONG_PRESS:
#                     """
#                     Switch to calibration mode
#                     """
#                     rot.BUTTON_LONG_PRESS = False
#                     calibrating_mode = True
#                     cal_readings = []  # to be populated with len==2 list of [known_weight, raw_reading] 
#                     kgs_mode = True
#                     rot.COUNTER = 0
#                     kgs = 0
#                     grams = 0
#                     lcd.clear_screen()
#                     button = rot.BUTTON_LAST_PRESS
#                 else:    
#                     """
#                     Print reading and target. Control stepper.
#                     """
#                     lcd.lcd_string("{:,.1f} kg".format(converted_reading), lcd.LCD_LINE_1)
#                     lcd.lcd_string("Target: {:,.1f} kg".format(target_kgs), lcd.LCD_LINE_2)
#                     # logic to drive the stepper
#                     if rot.BUTTON_LAST_PRESS == button:  # still in tensioning mode
#                         """
#                         Trigger tensioning logic
#                         """
#                         if converted_reading < target_kgs:
#                             if limit_switch.STATE:  # safe to proceed
#                                 # tighten stepper
#                                 direction = 1
#                                 n_steps = steps_per_rev * movement_mm / leadscrew_lead 
#                                 stepper.step(n_steps=n_steps, direction=direction)
#                             else:
#                                 # limit switch hit whilst tightening **assumption!!**
#                                 # therefore back off the limit switch by 10mm
#                                 direction = 0
#                                 n_steps = steps_per_rev * 10 / leadscrew_lead 
#                                 stepper.step(n_steps=n_steps, direction=direction)
#                         else:  # still in tensioning mode, but actual tension has overshot target tension
#                             if limit_switch.STATE:  # safe to proceed
#                                 # loosen stepper
#                                 direction = 0
#                                 n_steps = steps_per_rev * movement_mm / leadscrew_lead 
#                                 stepper.step(n_steps=n_steps, direction=direction)
#                             else:
#                                 """
#                                 Something is wrong. There is tension, but the tensioner
#                                 is up against the limit switch.
#                                 Back up 10mm, then back up until near limit switch is hit
#                                 Turn tensioning_mode off
#                                 """
#                                 lcd.lcd_string("*** ERROR ***", lcd.LCD_LINE_1)
#                                 lcd.lcd_string("LIMIT SWITCH ON", lcd.LCD_LINE_2)
#                                 tensioning_mode = False
#                                 direction = 0
#                                 n_steps = steps_per_rev * 10mm / leadscrew_lead 
#                                 stepper.step(n_steps=n_steps, direction=direction)
#                                 while limit_switch.STATE:
#                                     # loosen stepper until the limit switch is hit
#                                     direction = 0
#                                     n_steps = steps_per_rev * movement_mm / leadscrew_lead 
#                                     stepper.step(n_steps=n_steps, direction=direction)
#                                 # back off the limit switch by 10mm    
#                                 direction = 1
#                                 n_steps = steps_per_rev * 10 / leadscrew_lead 
#                                 stepper.step(n_steps=n_steps, direction=direction) 
#                     else:  #  Single press, release all tension and turn tensioning mode off
#                         tensioning_mode = False
#                         while limit_switch.STATE:
#                             # loosen stepper until the limit switch is hit
#                             direction = 0
#                             n_steps = steps_per_rev * movement_mm / leadscrew_lead 
#                             stepper.step(n_steps=n_steps, direction=direction)
#                         # back off the limit switch by 10mm    
#                         direction = 1
#                         n_steps = steps_per_rev * 10 / leadscrew_lead 
#                         stepper.step(n_steps=n_steps, direction=direction) 
#             elif calibrating_mode:
#                 while len(cal_readings) < 2:
#                     if len(cal_readings) == 0:
#                         lcd.lcd_string("Enter weight 1:", lcd.LCD_LINE_1)
#                     else:
#                         lcd.lcd_string("Enter weight 2:", lcd.LCD_LINE_1)
#                     while not rot.BUTTON_LONG_PRESS:
#                         if rot.BUTTON_LAST_PRESS != button:
#                             button = rot.BUTTON_LAST_PRESS
#                             kgs_mode = not kgs_mode
#                             if kgs_mode:
#                                 rot.COUNTER = kgs
#                             else:
#                                 rot.COUNTER = grams
#                         if kgs_mode:
#                             rot.COUNTER = max(0, min(99, rot.COUNTER))
#                             kgs = rot.COUNTER
#                         else:
#                             rot.COUNTER = max(0, min(9,rot.COUNTER))
#                             grams = rot.COUNTER
#                         known_weight = float("{}.{}".format(kgs, grams))    
#                         lcd.lcd_string("{} kgs".format(known_weight), lcd.LCD_LINE_2)
#                     rot.BUTTON_LONG_PRESS = False
#                     calibrating_mode = False    
#                     cal_readings.append([known_weight, hx.get_reading(n_obs=9, clip=True)])

#                 # now that we have two calibration readings:
#                 cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
#                         / (cal_readings[1][0] - cal_readings[0][0])
#                 cal_offset = cal_readings[1][1] - cal_factor * cal_readings[1][0]

#                 # store new calibration variables in config.py
#                 with open("config.py", "w") as f:
#                     f.write("cal_factor={}\ncal_offset={}".format(cal_factor, cal_offset))

#                 lcd.lcd_string("*"*16, lcd.LCD_LINE_1)
#                 lcd.lcd_string("*"*16, lcd.LCD_LINE_2)
#                 rot.COUNTER = target_kgs*10
#                 print("Calibration factor: {}\nCalibration offset: {}"
#                         .format(cal_factor, cal_offset))
#             else:  # neither tensioning nor calibrating
#                 """
#                 Print reading and target.
#                 """
#                 lcd.lcd_string("{:,.1f} kg".format(converted_reading), lcd.LCD_LINE_1)
#                 lcd.lcd_string("Target: {:,.1f} kg".format(target_kgs), lcd.LCD_LINE_2)


#     except KeyboardInterrupt:
#         pass
#     finally:
#         lcd.cleanup()
#         hx.cleanup()
#         pass
