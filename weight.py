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


if __name__ == "__main__":
    try:
        GPIO.setmode(GPIO.BCM)
        n_obs = 5
        target_kgs = 23.0
        hx = HX711(data=2, clock=3, channel="A", gain=128, printout=False)
        lcd = LCD1602(data_pins=[23,24,25,8], rs_pin=14, e_pin=15)
        rot = RotaryEncoder(clk=22, dt=27, button=17,
                counter=target_kgs*10, long_press_secs=1.0, debounce_n=2)
        button = rot.BUTTON_LAST_PRESS
        tension_toggle = Toggle(toggle_pin=4)
        limit_switch = Button(button_pin=10)
        # default calibration settings
        calibrating = False
        cal_factor = 91038.5
        cal_offset = 135222.4
        while True:
            if not calibrating:
                """
                Get reading in kgs, and target kgs
                """
                reading = hx.get_reading(n_obs=5, clip=True)
                converted_reading = max(
                        0,round((reading - cal_offset) / cal_factor,2))
                target_kgs = max(0, min(500, rot_COUNTER))/10
                if rot.BUTTON_LONG_PRESS:
                    """
                    Switch to calibration mode
                    """
                    rot.BUTTON_LONG_PRESS = False
                    calibrating = True
                    cal_readings = []  # to be populated with len==2 list of [known_weight, raw_reading] 
                    kgs_mode = True
                    rot.COUNTER = 0
                    kgs = 0
                    grams = 0
                    lcd.clear_screen()
                    button = rot.BUTTON_LAST_PRESS
                else:    
                    """
                    Print reading and target
                    """
                    lcd.lcd_string("{:,.1f} kg".format(converted_reading), lcd.LCD_LINE_1)
                    lcd.lcd_string("Target: {:,.1f} kg".format(target_kgs), lcd.LCD_LINE_2)
                    # logic to drive the stepper
                    if tension_toggle.is_on:
                        """
                        Trigger tensioning logic
                        """
                        if converted_reading < target_kgs:
                            # tighten stepper
                        else:
                            if not limit_switch.is_on(debounce_pause=0.04):
                                # loosen stepper
                            else:
                                """
                                Something is wrong. There is tension, but the tensioner
                                is up against the limit switch
                                """
                                lcd.lcd_string("*** ERROR ***", lcd.LCD_LINE_1)
                                lcd.lcd_string("LIMIT SWITCH ON", lcd.LCD_LINE_2)
                    else:
                        if not limit_switch.is_on(debounce_pause=0.04):
                            # loosen stepper unless already up against the limit switch

            else:        
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
                    calibrating = False    
                    cal_readings.append([known_weight, hx.get_reading(n_obs=9, clip=True)])
                # now that we have two calibration readings:
                cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
                        / (cal_readings[1][0] - cal_readings[0][0])
                cal_offset = cal_readings[1][1] - cal_factor * cal_readings[1][0]
                lcd.lcd_string("*"*16, lcd.LCD_LINE_1)
                lcd.lcd_string("*"*16, lcd.LCD_LINE_2)
                rot.COUNTER = target_kgs*10
                print("Calibration factor: {}\nCalibration offset: {}"
                        .format(cal_factor, cal_offset))


    except KeyboardInterrupt:
        pass
    finally:
        lcd.cleanup()
        hx.cleanup()
        pass
