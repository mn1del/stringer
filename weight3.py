#!/usr/bin/env python


if __name__ == "__main__":

   import time
   import pigpio
   import HX711

   def cbf(count, mode, reading):
      print(count, mode, reading)

   pi = pigpio.pi()
   if not pi.connected:
      exit(0)

   s = HX711.sensor(
      pi, DATA=5, CLOCK=6, mode=HX711.CH_B_GAIN_32, callback=cbf)

   try:
      print("start with CH_B_GAIN_32 and callback")

      time.sleep(2)

      s.set_mode(HX711.CH_A_GAIN_64)

      print("Change mode to CH_A_GAIN_64")

      time.sleep(2)

      s.set_mode(HX711.CH_A_GAIN_128)

      print("Change mode to CH_A_GAIN_128")

      time.sleep(2)

      s.pause()

      print("Pause")

      time.sleep(2)

      s.start()

      print("Start")

      time.sleep(2)

      s.set_callback(None)

      s.set_mode(HX711.CH_A_GAIN_128)

      print("Change mode to CH_A_GAIN_128")

      print("Cancel callback and read manually")

      c, mode, reading = s.get_reading()

      stop = time.time() + 3600

      while time.time() < stop:

         count, mode, reading = s.get_reading()

         if count != c:
            c = count
            print("{} {} {}".format(count, mode, reading))

         time.sleep(0.05)

   except KeyboardInterrupt:
      pass

   s.pause()

   s.cancel()

   pi.stop()

