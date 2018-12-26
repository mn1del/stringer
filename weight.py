#!/usr/bin/env python


import time
import pigpio
import HX711


def cbf(count, mode, reading):
    print("callback: {}, {}, {}".format(count, mode, reading))

class HX(HX711.sensor):
    def __init__(self, pi, DATA=5, CLOCK=6, mode=HX711.CH_B_GAIN_32, callback=cbf):
        super().__init__(pi, DATA=5, CLOCK=6, mode=HX711.CH_B_GAIN_32, callback=cbf)

    def print10x(self, val):
        print("10x: {}".format(val * 10))

    def saven(self, n):
        self.n = n

    def printnx(self, val):
        print("nx: {}".format(self.n * val))

if __name__ == "__main__":


   pi = pigpio.pi()
   if not pi.connected:
      exit(0)

   s = HX(pi, DATA=5, CLOCK=6, mode=HX711.CH_B_GAIN_32, callback=cbf)
   #s = HX711.sensor(
   #   pi, DATA=5, CLOCK=6, mode=HX711.CH_B_GAIN_32, callback=cbf)

   try:
      print("start with CH_B_GAIN_32 and callback")

      time.sleep(1)

      s.set_mode(HX711.CH_A_GAIN_64)

      print("Change mode to CH_A_GAIN_64")

      time.sleep(1)

      s.set_mode(HX711.CH_A_GAIN_128)

      print("Change mode to CH_A_GAIN_128")

      time.sleep(1)

      s.pause()

      print("Pause")

      time.sleep(1)

      s.start()

      print("Start")

      time.sleep(1)

      s.set_callback(None)

      s.set_mode(HX711.CH_A_GAIN_128)

      print("Change mode to CH_A_GAIN_128")

      print("Cancel callback and read manually")

      c, mode, reading = s.get_reading()

      stop = time.time() + 3600

      s.saven(0.1)
      s.print10x(10)

      while time.time() < stop:

         count, mode, reading = s.get_reading()

         if count != c:
            c = count
            print("{} {} {}".format(count, mode, reading))
            s.printnx(reading)

         time.sleep(0.05)

   except KeyboardInterrupt:
      pass

   s.pause()

   s.cancel()

   pi.stop()

