#!/usr/bin/env python3


from hx711 import HX711
import RPi.GPIO as GPIO
import argparse

def main():
    try:
    # Create an object hx which represents your real hx711 chip
    # Required input parameters are only 'dout_pin' and 'pd_sck_pin'
    # If you do not pass any argument 'gain_channel_A' then the default value is 128
    # If you do not pass any argument 'set_channel' then the default value is 'A'
    # you can set a gain for channel A even though you want to currently select channel B
        hx = HX711(dout_pin=29, pd_sck_pin=31, gain_channel_A=ARGS["gain"])

        result = hx.reset()  # Before we start, reset the hx711 ( not necessary)

        if result:  # you can check if the reset was successful
            print('Ready to use')
        else:
            print('not ready')
    
        # Read data several, or only one, time and return value
        # it just returns exactly the number which hx711 sends
        # argument times is not required default value is 1
        if ARGS["median"]:
            data = hx.get_raw_data_median(times=1)
        else:
            data = hx.get_raw_data_mean(times=1)
        
        if data != False:  # always check if you get correct value or only False
            print('Raw data: ' + str(data))
        else:
            print('invalid data')
    
        # measure tare and save the value as offset for current channel
        # and gain selected. That means channel A and gain 64
        result = hx.zero(times=ARGS["times"])
    
        # Read data several, or only one, time and return avg value.
        # It subtracts offset value for particular channel from the avg value.
        # This value is still just a number from HX711 without any conversion
        # to units such as grams or kg.
        if ARGS["median"]:
            data = hx.get_data_median(times=ARGS["times"])
        else:
            data = hx.get_data_mean(times=ARGS["times"])
    
        if data  != False:  # always check if you get correct value or only False
            # now the value is close to 0
            print('Data subtracted by offset but still not converted to any unit: '\
                 + str(data))
        else:
            print('invalid data')
            
        # In order to calculate the conversion ratio to some units, in my case I want grams,
        # you must have known weight.
        input('Put known weight on the scale and then press Enter')
        if ARGS["debug"]:
            hx.set_debug_mode(True)
        else:
            hx.set_debug_mode(False)

        if ARGS["median"]:
            data = hx.get_data_median(times=ARGS["times"])
        else:
            data = hx.get_data_mean(times=ARGS["times"])

        if data != False:
            print('Mean value from HX711 subtracted by offset: ' + str(data))
            known_weight_grams = input('Write how many grams it was and press Enter: ')
            try:
                value = float(known_weight_grams)
                print(str(value) + ' grams')
            except ValueError:
                print('Expected integer or float and I have got: '\
                        + str(known_weight_grams))
    
            # set scale ratio for particular channel and gain which is 
            # used to calculate the conversion to units. To set this 
            # you must have known weight first. Required argument is only
            # scale ratio. Without arguments 'channel' and 'gain_A' it sets 
            # the ratio for current channel and gain.
            ratio = data / value     # calculate the ratio for channel A and gain 64
            hx.set_scale_ratio(scale_ratio=ratio)    # set ratio for current channel
            print('Ratio is set.')
        else:
            raise ValueError('Cannot calculate avg value. Try debug mode.')
    
        # Read data several, or only one, time and return avg value
        # subtracted by offset and converted by scale ratio to 
        # desired units. In my case in grams.
        # print('Current weight on the scale in grams is: ')
        while True:
            result = hx.reset()  # Before we start, reset the hx711 ( not necessary)
    
            while True:
                if result:  # you can check if the reset was successful
                    break
                else:
                    result = hx.reset()  # Before we start, reset the hx711 ( not necessary)

            if ARGS["median"]:
                print(str(hx.get_weight_median(ARGS["times"])) + ' g') 
            else:
                #print(str(hx.get_weight_mean(ARGS["times"])) + ' g') 
                print(str(hx.get_raw_data_mean(times=1)) + ' g') 

    except (KeyboardInterrupt, SystemExit):
        print('Bye :)')
        
    finally:
        print("Cleanup")
        GPIO.cleanup()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--times", nargs="?", const=10, default=10, required=False)
    parser.add_argument("-m", "--median", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-g", "--gain", nargs="?", type=int, const=128, default=128, choices=[64,128])
    ARGS = vars(parser.parse_args())
    print(ARGS)
    main()
