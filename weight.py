#!/usr/bin/env python3


import sys
import os

sys.path.append(os.path.abspath(os.path.join("..", "rpigpio")))
from hx711 import HX711
from lcd1602 import LCD1602


if __name__ == "__main__":
    try:
        n_obs = 5
        hx = HX711(printout=False)
        hx.start_monitoring(n_obs=n_obs)
        lcd = LCD1602()
        while True:
            print("Reading (avg of {}): {}".format(n_obs, hx.AVG_READING))
            lcd.lcd_string("Reading:", lcd.LCD_LINE_1)
            lcd.lcd_string(hx.AVG_READING, lcd.LCD_LINE_2)
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()
