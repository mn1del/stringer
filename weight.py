#!/usr/bin/env python3


import sys
import os
import time
import RPi.GPIO as GPIO

sys.path.append(os.path.abspath(os.path.join("..", "rpigpio")))
from hx711 import HX711
from lcd1602 import LCD1602
from rotaryencoder import RotaryEncoder


if __name__ == "__main__":
    try:
        GPIO.setmode(GPIO.BCM)
        n_obs = 5
        hx = HX711(printout=False)
        lcd = LCD1602()
        rot = RotaryEncoder()
        button = rot.BUTTON_LAST_PRESS
        calibrating = False
        #kgs_mode = True
        #kgs = 0
        #grams = 0
        cal_factor = 1.0 
        cal_offset = 0.0
        while True:
            if not calibrating:
                reading = hx.get_reading(5)
                converted_reading = reading * cal_factor + cal_offset
                if rot.BUTTON_LONG_PRESS:
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
                    lcd.lcd_string("Reading:", lcd.LCD_LINE_1)
                    lcd.lcd_string("{:,.3f}".format(converted_reading), lcd.LCD_LINE_2)
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
                            kgs = rot.COUNTER # max(0, min(99, rot.COUNTER))
                        else:
                            rot.COUNTER = max(0, min(9,rot.COUNTER))
                            grams = rot.COUNTER # max(0, min(9,rot.COUNTER))
                        known_weight = float("{}.{}".format(kgs, grams))    
                        lcd.lcd_string("{} kgs".format(known_weight), lcd.LCD_LINE_2)
                    rot.BUTTON_LONG_PRESS = False
                    lcd.lcd_string("*"*16, lcd.LCD_LINE_1)
                    lcd.lcd_string("*"*16, lcd.LCD_LINE_2)
                    calibrating = False    
                    cal_readings.append([known_weight, hx.get_reading(30)])
                # now that we have two calibration readings:
                cal_factor = (cal_readings[1][1] - cal_readings[0][1]) \
                        / (cal_readings[1][0] - cal_readings[0][0])
                cal_offset = cal_readings[1][1] - cal_factor * cal_readings[1][0]


    except KeyboardInterrupt:
        pass
    finally:
        lcd.cleanup()
        hx.cleanup()
        pass
