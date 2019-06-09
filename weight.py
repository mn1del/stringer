#!/usr/bin/env python3


import sys
import os
import time
import RPi.GPIO as GPIO
from multiprocessing.dummy import threading

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
        self.target_kgs = 25.0
        self.stall_safe_kgs = 20  # only increment safe fast retract distance if the weight is less than this
        self.FAST_RETRACT_MM = 0  # safe distance to travel when going home (function of speed and weight)
        self.movement_mm = 0.05  # distance to increment the leadscrew
        self.limit_backoff_mm = 10  # distance to back off the limit switch when triggered
        self.leadscrew_lead = 2
        self.stepper_full_steps_per_rev = 200
        self.microstep_mode = 4 
        self.acceleration = 300
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
        self.near_limit_switch = Button(button_pin=23, pull_up=True, debounce_delay_secs=0.01)  
        self.far_limit_switch = Button(button_pin=24, pull_up=True, debounce_delay_secs=0.01)  
        self.stepper = Stepper(
                dir_pin=8, 
                step_pin=7, 
                sleep_pin=25,
                ms0_pin=21, 
                ms1_pin=20, 
                ms2_pin=16,
                steps_per_rev=self.stepper_full_steps_per_rev * self.microstep_mode,
                acceleration=self.acceleration,
                starting_rpm=6,
                microstep_mode=self.microstep_mode,
                driver="drv8825")
        self.NEAR_LIMIT_TRIGGERED = False
        self.FAR_LIMIT_TRIGGERED = False

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
            # start threads:
            self.RUN_THREADS = True
            limit_thread = threading.Thread(target=self.monitor_limit_switches)
            limit_thread.start()
            kgs_thread = threading.Thread(target=self.monitor_current_kgs)
            kgs_thread.start()
            # go to the home location of the tensioner
            self.go_home() 
            while True:
                if self.MODE == "resting":
                    self.rest()
                elif self.MODE == "tensioning":
                    self.tension()
                elif self.MODE == "calibrating":
                    self.calibrate()
                else:
                    print("Unknown mode!")
        except:
            # code to cleanup here
            self.RUN_THREADS = False
            self.stepper.sleep()
            self.lcd.clear_screen()
            print("Something went wrong in the master loop")
            pass
        finally:
            self.RUN_THREADS = False
            self.stepper.sleep()
            self.lcd.clear_screen()
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
                self.button = self.rot.BUTTON_LAST_PRESS
                if self.rot.BUTTON_LONG_PRESS:
                    self.MODE = "calibrating"
                else:
                    self.MODE = "tensioning"
        
    def tension(self):
        """
        Initialize rotary encoder counter with target_kgs and start tensioning logic loop.
        target_kgs can be dynamically managed with the rotary encoder.
        """
        print("In tensioning mode")
        self.rot.COUNTER = self.target_kgs*10
        cumulative_movement = 0
        # start tensioning lcd thread
        tensioning_lcd_thread = threading.Thread(target=self.tensioning_helper_thread)
        tensioning_lcd_thread.start()
        
        while self.MODE == "tensioning":
            print("Move: {:,.3f}mm, Cumulative movement: {:,.3f}mm, Kgs: {:,.2f}, target: {:,.2f}".format(
                self.MOVEMENT, cumulative_movement, self.CURRENT_KGS, self.target_kgs))

            if self.NEAR_LIMIT_TRIGGERED | self.FAR_LIMIT_TRIGGERED:
                self.MODE = "resting"
                self.lcd.lcd_string("**** Error ****", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string("** Limit Hit **", self.lcd.LCD_LINE_2)
                time.sleep(0.5)
                self.go_home()
            else:  # tighten/loosen
                if self.CURRENT_KGS < self.target_kgs:
                    cumulative_movement += self.MOVEMENT
                    if (self.CURRENT_KGS <= self.stall_safe_kgs):
                        self.FAST_RETRACT_MM += self.MOVEMENT
                    self.increment_stepper(1, self.MOVEMENT, mm_per_sec=4)
                elif self.CURRENT_KGS > self.target_kgs:
                    cumulative_movement += self.MOVEMENT
                    self.FAST_RETRACT_MM += self.MOVEMENT
                    self.increment_stepper(-1, self.MOVEMENT, mm_per_sec=4)
            if self.rot.BUTTON_LAST_PRESS != self.button:
                self.button = self.rot.BUTTON_LAST_PRESS
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
                if (self.limit_switch_triggered(self.near_limit_switch)) \
                        | (self.limit_switch_triggered(self.far_limit_switch)):
                    self.lcd.lcd_string("**** Error ****", self.lcd.LCD_LINE_1)
                    self.lcd.lcd_string("** Limit Hit **", self.lcd.LCD_LINE_2)
                    time.sleep(0.5)
                    self.go_home()
                    self.MODE = "resting"
                else:
                    if self.rot.COUNTER < counter:
                        direction = -1
                        self.increment_stepper(direction, self.movement_mm)
                    elif self.rot.COUNTER > counter:
                        direction = 1
                        self.increment_stepper(direction, self.movement_mm)
                    counter = self.rot.COUNTER
                    if self.rot.BUTTON_LAST_PRESS != self.button:
                        self.button = self.rot.BUTTON_LAST_PRESS
                        calibration_step = 1
            self.rot.COUNTER = 200  # 20 kgs starting default
            while calibration_step == 1:  # enter known weight
                self.lcd.lcd_string("known tension:", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string(
                    "{:,.1f} kgs".format(max(0,min(500, self.rot.COUNTER))/10), 
                    self.lcd.LCD_LINE_2)
                if self.rot.BUTTON_LAST_PRESS != self.button:
                    self.button = self.rot.BUTTON_LAST_PRESS
                    known_weight = self.rot.COUNTER/10
                    cal_readings.append([known_weight, self.hx.get_reading(n_obs=9, clip=True)])
                    self.go_home(suppress_message=True)
                    calibration_step = 2
            while calibration_step == 2:  # zero weight
                self.lcd.lcd_string("press when", self.lcd.LCD_LINE_1)
                self.lcd.lcd_string("tension is zero", self.lcd.LCD_LINE_2)
                if self.rot.BUTTON_LAST_PRESS != self.button:
                    self.button = self.rot.BUTTON_LAST_PRESS
                    known_weight = 0
                    cal_readings.append([known_weight, self.hx.get_reading(n_obs=9, clip=True)])
                    calibration_step = 3

            # now that we have two calibration readings:
            self.cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
                    / (cal_readings[1][0] - cal_readings[0][0])
            self.cal_offset = cal_readings[1][1] - self.cal_factor * cal_readings[1][0]
            # store new calibration variables in config.py
            with open("config.py", "w") as f:
                f.write("cal_factor={}\ncal_offset={}".format(self.cal_factor, self.cal_offset))
            self.MODE = "resting"    
        
    def go_home(self, suppress_message=False):
        """
        Returns the tensioner to its home position, using the limit switch as a guide.
        Sets HOME state.
        
        args:
            far_limit_back_off_mm: (float) mm to back off the far limit switch first.
                                   Default zero results in no initial far limit backoff
            suppress_message: (bool) If True, do not display "RETURNING HOME" status                        
        """
        print("far limit: {}\nnear limit: {}".format(self.FAR_LIMIT_TRIGGERED, self.NEAR_LIMIT_TRIGGERED))
        # initial back off from far limit switch:
        if self.FAR_LIMIT_TRIGGERED:
            self.increment_stepper(direction=-1, movement_mm=self.limit_backoff_mm, mm_per_sec=5)
        # Display status
        if not suppress_message:
            self.lcd.lcd_string("***RETURNING***", self.lcd.LCD_LINE_1)
            self.lcd.lcd_string("*****HOME******", self.lcd.LCD_LINE_2)
        # initial fast retract
        self.increment_stepper(direction=-1, movement_mm=self.FAST_RETRACT_MM, mm_per_sec=5)
        self.FAST_RETRACT_MM = 0
        # increment backwards until near limit triggered:
        while not self.NEAR_LIMIT_TRIGGERED:
            self.increment_stepper(direction=-1, movement_mm=0.5, mm_per_sec=5)
        # finally back off near limit switch     
        print("HERE!")
        self.increment_stepper(direction=1, movement_mm=self.limit_backoff_mm, mm_per_sec=6)
        self.HOME = True
        
    def raw_to_kgs(self, raw):
        """
        converts the raw HX711 reading to kgs
        
        args:
            raw: raw HX711 reading
        """
        kgs = max(0,(raw - self.cal_offset) / self.cal_factor)
        return kgs
    
    def increment_stepper(self, direction, movement_mm, mm_per_sec=5):
        """
        Helper function to increment the leadscrew forwards.
        Sets HOME to False, to register that the position has changed.
        Also has safety logic to check against the limit switches.
        
        args:
        direction: (int) 1 or -1. 1 for tightening motion. -1 for loosening
        movement_mm: (float) movement in mm to increment the leadscrew. 
                     Defaults to self.movement_mm
        mm_per_sec: (int) determines inter step pause length             
        """
        rpm = 60 * mm_per_sec/self.leadscrew_lead    
        direction = int((direction + 1) / 2)  # convert to 0|1   
        n_steps = int(self.stepper_full_steps_per_rev * self.microstep_mode * movement_mm
                / self.leadscrew_lead)
#        if (direction==1) & (self.FAR_LIMIT_TRIGGERED==False):
#            self.stepper.step(
#                    n_steps=n_steps,
#                    direction=direction,
#                    rpm=rpm,
#                    use_ramp=True)
#        elif (direction==0) & (self.NEAR_LIMIT_TRIGGERED==False):
#            self.stepper.step(
#                    n_steps=n_steps,
#                    direction=direction,
#                    rpm=rpm,
#                    use_ramp=True)
        self.stepper.step(
                    n_steps=n_steps,
                    direction=direction,
                    rpm=rpm,
                    use_ramp=True)
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
        
    def monitor_limit_switches(self):
        """
        Constantly monitors the state of the limit switches. Sets the 
        state of self.NEAR_LIMIT_TRIGGERED and self.FAR_LIMIT_TRIGGERED accordingly
        """
        while self.RUN_THREADS:
            time.sleep(0.005)
            if self.limit_switch_triggered(self.near_limit_switch):
                self.NEAR_LIMIT_TRIGGERED = True
            else:    
                self.NEAR_LIMIT_TRIGGERED = False
            if self.limit_switch_triggered(self.far_limit_switch):
                self.FAR_LIMIT_TRIGGERED = True
            else:    
                self.FAR_LIMIT_TRIGGERED = False

    def monitor_current_kgs(self):
        """
        Constantly monitors the HX711 reading and stores the converted state in self.CURRENT_KGS.
        """
        while self.RUN_THREADS:
            time.sleep(0.005)
            raw = self.hx.get_reading(n_obs=3, clip=True)
            kgs = max(0,(raw - self.cal_offset) / self.cal_factor)
            self.CURRENT_KGS = kgs

    def calc_tensioning_movement(self):
        """
        Constantly calculates next movement_mm, depending on self.MODE, self.CURRENT_KGS, and self.target_kgs.
        Runs in its own thread to reduce latency between stepper motor commands.
        """
        movement_factor = 10 * self.target_kgs
        while self.RUN_THREADS:
            movement_factor = max(0.5, min(movement_factor*1.2, abs(self.CURRENT_KGS - self.target_kgs)*10))
            if self.CURRENT_KGS >= 22:
                movement = min(0.5, 0.05 * movement_factor)
            else:    
                movement = 0.1 * movement_factor
            self.MOVEMENT = movement    

    def tensioning_helper_thread(self):
        """
        Designed to dynamically display tension data in a separate thread while the motor runs in the main
        thread. 
        """
        while (self.RUN_THREADS) & (self.MODE == "tensioning"):
            self.target_kgs = max(0,min(500, self.rot.COUNTER))/10
            self.lcd.lcd_string("Target: {:,.1f} kg".format(self.target_kgs), self.lcd.LCD_LINE_1)
            self.lcd.lcd_string("Actual: {:,.1f} kg".format(self.CURRENT_KGS), self.lcd.LCD_LINE_2)
        
if __name__ == "__main__":
    stringer = Stringer()
    stringer.start()
