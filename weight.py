#!/usr/bin/env python


import time
import pigpio
import HX711


def cbf(count, mode, reading):
    print("callback: {}, {}, {}".format(count, mode, reading))

class HX(HX711.sensor):
    #def __init__(self, pi, DATA=5, CLOCK=6, mode=HX711.CH_A_GAIN_128, callback=None):
    #    super().__init__(pi=pi, DATA=DATA, CLOCK=CLOCK, mode=mode, callback=callback)

    def zero(self, zero_reading):
        self.offset = reading

    def calibrate(self, known_weight, reading):
        print("weight, reading, offset: {} {} {}".format(known_weight, reading, self.offset))
        self.slope = known_weight/(reading - self.offset)

    def get_weight(self, reading):
        return self.slope * (reading - self.offset)

if __name__ == "__main__":
   pi = pigpio.pi()
   if not pi.connected:
      exit(0)

   s = HX(pi, DATA=5, CLOCK=6, mode=HX711.CH_A_GAIN_128, callback=cbf)

   try:
      print("Initialized...")
      timestamp = time.time()
      reading = 1
      while True:
          c,m,r = s.get_reading()
          if r != reading:
              newtime = time.time()
              reading = r
              print("{}s: reading: {}".format(
                  round(newtime-timestamp, 3), reading))
              timestamp = newtime
          #time.sleep(0.5)    

   except KeyboardInterrupt:
      pass

   s.pause()

   s.cancel()

   pi.stop()

