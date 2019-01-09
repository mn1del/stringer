#!/usr/bin/env python3


import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join("..", "rpigpio")))
from hx711 import HX711
from lcd1602 import LCD1602
from rotaryencoder import RotaryEncoder


if __name__ == "__main__":
    try:
        n_obs = 5
        hx = HX711(printout=False)
        lcd = LCD1602()
        rot = RotaryEncoder()
        counter = rot.COUNTER
        button = rot.BUTTON_LAST_PRESS
        while True:
            reading = hx.get_reading(5)
            if not rot.BUTTON_LONG_PRESS:
                lcd.lcd_string("Reading:", lcd.LCD_LINE_1)
                lcd.lcd_string("{:,.3f}".format(reading), lcd.LCD_LINE_2)
            if (rot.BUTTON_LAST_PRESS != button) & (rot.BUTTON_LONG_PRESS):
                button = rot.BUTTON_LAST_PRESS
                lcd.clear_screen()
                lcd.lcd_string("Long press:", lcd.LCD_LINE_1)


    except KeyboardInterrupt:
        pass
    finally:
        lcd.cleanup()
        hx.cleanup()
        pass
