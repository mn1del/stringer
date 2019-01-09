#!/usr/bin/env python3


import sys
import os

sys.path.append(os.path.abspath(r"..\rpigpio"))
from hx711 import HX711
from lcd1602 import LCD1602


if __name__ == "__main__":
    try:
        hx = HX711(printout=True)
        hx.start_monitoring(n_obs=5)
        lcd = LCD1602()
        while True:
            lcd.lcd_string("Reading:", lcd.LCD_LINE_1)
            lcd.lcd_string(hx.AVG_READING, lcd.LCD_LINE_2)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
