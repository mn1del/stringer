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
    def __init__():
        """
        Hardware and behaviour of the stringer. 
        """
        # setup hardware
        GPIO.setmode(GPIO.BCM)
        self.n_obs = 5
        self.target_kgs = 23.0
        self.movement_mm = 0.25  # distance to increment the leadscrew
        self.leadscrew_lead = 2
        self.hx = HX711(data=3, clock=2, channel="A", gain=128, printout=False)
        self.lcd = LCD1602(data_pins=[6,13,19,26], rs_pin=11, e_pin=5)
        self.rot = RotaryEncoder(clk=7, dt=8, button=25,
                                 counter=target_kgs*10, long_press_secs=1.0, debounce_n=2)
        self.button = rot.BUTTON_LAST_PRESS
        self.limit_switch = Button(button_pin=15, pull_up=True, debounce_delay_secs=0.01)
        self.stepper = Stepper(
                dir_pin=8, 
                step_pin=7, 
                sleep_pin=25,
                ms1_pin=21, 
                ms2_pin=20, 
                ms3_pin=16,
                steps_per_rev=200,
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
            self.MODE = "monitoring"
        self.go_home()  # go to the home location of the tensioner
        
        # start loop:
        try:
            while True:
                if self.MODE == "monitoring":
                    self.monitor()
                elif self.MODE == "tensioning":
                    self.tension()
                elif self.MODE == "calibrating":
                    self.calibrate
                else:
                    print("Unknown mode!")
        except KeyboardInterrupt:
            # code to cleanup here
        finally:
            GPIO.cleanup()
                   
        
    def monitor(self):
        """
        1) Set self.rot.COUNTER = self.target_kgs * 10
        2) Brings the tensioner to HOME position & set self.HOME=True  # only if self.HOME==False
        3) Change the stepper status to SLEEP.
        
        Then, while self.MODE=="monitoring":  # loop:
        4) Display self.target_kgs
        5) Set self.target_kgs = self.rot.COUNTER / 10
        6) if self.rot.BUTTON_LAST_PRESS != self.button:
                if self.rot.BUTTON_LONG_PRESS:
                    self.MODE = "calibrating"
                else:
                    self.MODE = "tensioning"
        """
        
    def tension(self):
        """
        pseudo code:
        -Get current HX711 reading
        self.rot.COUNTER = self.target_kgs*10
        
        While self.MODE == "tensioning":
            -Get current reading
            self.target_kgs = self.rot.COUNTER / 10
            -Display Target & current reading
            If limit not hit:
                if current < self.target_kgs:
                    tighten
                elif current > self.target_kgs:
                    loosen
            else:  # (limit hit)        
                Display Error Message
                self.go_home()
                self.MODE = "monitoring"
            if self.rot.BUTTON_LAST_PRESS != self.button:
                if self.rot.BUTTON_LONG_PRESS:
                    self.MODE = "calibrating"
                else:
                    self.go_home()
                    self.MODE = "monitoring"
        """
        
    def calibrate(self):
        """
        """
        
    def go_home(self):
        """
        Move stepper back until limit is hit, then back off 10mm
        self.HOME = True
        """

if __name__ == "__main__":
    try:
        GPIO.setmode(GPIO.BCM)
        n_obs = 5
        target_kgs = 23.0
        movement_mm = 0.25  # distance to increment the leadscrew
        leadscrew_lead = 2
        hx = HX711(data=3, clock=2, channel="A", gain=128, printout=False)
        lcd = LCD1602(data_pins=[6,13,19,26], rs_pin=11, e_pin=5)
        rot = RotaryEncoder(clk=7, dt=8, button=25,
                counter=target_kgs*10, long_press_secs=1.0, debounce_n=2)
        button = rot.BUTTON_LAST_PRESS
        tensioning_mode = False
        limit_switch = Button(button_pin=15, pull_up=True, debounce_delay_secs=0.01)
        stepper = Stepper(
                dir_pin=8, 
                step_pin=7, 
                sleep_pin=25,
                ms1_pin=21, 
                ms2_pin=20, 
                ms3_pin=16,
                steps_per_rev=200,
                microstep_mode=2,
                driver="drv8825")
        # default calibration settings
        calibrating_mode = False
        cal_factor = config.cal_factor
        cal_offset = config.cal_offset
        while True:
            """
            Get reading in kgs, and target kgs
            """
            reading = hx.get_reading(n_obs=5, clip=True)
            converted_reading = max(
                    0,round((reading - cal_offset) / cal_factor,2))
            target_kgs = max(0, min(500, rot_COUNTER))/10
            if tensioning_mode:
                if rot.BUTTON_LONG_PRESS:
                    """
                    Switch to calibration mode
                    """
                    rot.BUTTON_LONG_PRESS = False
                    calibrating_mode = True
                    cal_readings = []  # to be populated with len==2 list of [known_weight, raw_reading] 
                    kgs_mode = True
                    rot.COUNTER = 0
                    kgs = 0
                    grams = 0
                    lcd.clear_screen()
                    button = rot.BUTTON_LAST_PRESS
                else:    
                    """
                    Print reading and target. Control stepper.
                    """
                    lcd.lcd_string("{:,.1f} kg".format(converted_reading), lcd.LCD_LINE_1)
                    lcd.lcd_string("Target: {:,.1f} kg".format(target_kgs), lcd.LCD_LINE_2)
                    # logic to drive the stepper
                    if rot.BUTTON_LAST_PRESS == button:  # still in tensioning mode
                        """
                        Trigger tensioning logic
                        """
                        if converted_reading < target_kgs:
                            if limit_switch.STATE:  # safe to proceed
                                # tighten stepper
                                direction = 1
                                n_steps = steps_per_rev * movement_mm / leadscrew_lead 
                                stepper.step(n_steps=n_steps, direction=direction)
                            else:
                                # limit switch hit whilst tightening **assumption!!**
                                # therefore back off the limit switch by 10mm
                                direction = 0
                                n_steps = steps_per_rev * 10 / leadscrew_lead 
                                stepper.step(n_steps=n_steps, direction=direction)
                        else:  # still in tensioning mode, but actual tension has overshot target tension
                            if limit_switch.STATE:  # safe to proceed
                                # loosen stepper
                                direction = 0
                                n_steps = steps_per_rev * movement_mm / leadscrew_lead 
                                stepper.step(n_steps=n_steps, direction=direction)
                            else:
                                """
                                Something is wrong. There is tension, but the tensioner
                                is up against the limit switch.
                                Back up 10mm, then back up until near limit switch is hit
                                Turn tensioning_mode off
                                """
                                lcd.lcd_string("*** ERROR ***", lcd.LCD_LINE_1)
                                lcd.lcd_string("LIMIT SWITCH ON", lcd.LCD_LINE_2)
                                tensioning_mode = False
                                direction = 0
                                n_steps = steps_per_rev * 10mm / leadscrew_lead 
                                stepper.step(n_steps=n_steps, direction=direction)
                                while limit_switch.STATE:
                                    # loosen stepper until the limit switch is hit
                                    direction = 0
                                    n_steps = steps_per_rev * movement_mm / leadscrew_lead 
                                    stepper.step(n_steps=n_steps, direction=direction)
                                # back off the limit switch by 10mm    
                                direction = 1
                                n_steps = steps_per_rev * 10 / leadscrew_lead 
                                stepper.step(n_steps=n_steps, direction=direction) 
                    else:  #  Single press, release all tension and turn tensioning mode off
                        tensioning_mode = False
                        while limit_switch.STATE:
                            # loosen stepper until the limit switch is hit
                            direction = 0
                            n_steps = steps_per_rev * movement_mm / leadscrew_lead 
                            stepper.step(n_steps=n_steps, direction=direction)
                        # back off the limit switch by 10mm    
                        direction = 1
                        n_steps = steps_per_rev * 10 / leadscrew_lead 
                        stepper.step(n_steps=n_steps, direction=direction) 
            elif calibrating_mode:
                while len(cal_readings) < 2:
                    if len(cal_readings) == 0:
                        lcd.lcd_string("Enter weight 1:", lcd.LCD_LINE_1)
                    else:
                        lcd.lcd_string("Enter weight 2:", lcd.LCD_LINE_1)
                    while not rot.BUTTON_LONG_PRESS:
                        if rot.BUTTON_LAST_PRESS != button:
                            button = rot.BUTTON_LAST_PRESS
                            kgs_mode = not kgs_mode
                            if kgs_mode:
                                rot.COUNTER = kgs
                            else:
                                rot.COUNTER = grams
                        if kgs_mode:
                            rot.COUNTER = max(0, min(99, rot.COUNTER))
                            kgs = rot.COUNTER
                        else:
                            rot.COUNTER = max(0, min(9,rot.COUNTER))
                            grams = rot.COUNTER
                        known_weight = float("{}.{}".format(kgs, grams))    
                        lcd.lcd_string("{} kgs".format(known_weight), lcd.LCD_LINE_2)
                    rot.BUTTON_LONG_PRESS = False
                    calibrating_mode = False    
                    cal_readings.append([known_weight, hx.get_reading(n_obs=9, clip=True)])

                # now that we have two calibration readings:
                cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
                        / (cal_readings[1][0] - cal_readings[0][0])
                cal_offset = cal_readings[1][1] - cal_factor * cal_readings[1][0]

                # store new calibration variables in config.py
                with open("config.py", "w") as f:
                    f.write("cal_factor={}\ncal_offset={}".format(cal_factor, cal_offset))

                lcd.lcd_string("*"*16, lcd.LCD_LINE_1)
                lcd.lcd_string("*"*16, lcd.LCD_LINE_2)
                rot.COUNTER = target_kgs*10
                print("Calibration factor: {}\nCalibration offset: {}"
                        .format(cal_factor, cal_offset))
            else:  # neither tensioning nor calibrating
                """
                Print reading and target.
                """
                lcd.lcd_string("{:,.1f} kg".format(converted_reading), lcd.LCD_LINE_1)
                lcd.lcd_string("Target: {:,.1f} kg".format(target_kgs), lcd.LCD_LINE_2)


    except KeyboardInterrupt:
        pass
    finally:
        lcd.cleanup()
        hx.cleanup()
        pass
