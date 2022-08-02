import machine
import rp2
import network
import ubinascii
import time
import sys
from secrets import secrets
from onewire import OneWire
from ds18x20 import DS18X20
from umqtt.simple import MQTTClient
from machine import Pin


#pin declaration
led = machine.Pin('LED', machine.Pin.OUT)
sw = machine.Pin(19,machine.Pin.IN,machine.Pin.PULL_UP)
#first set PIN27 to be IN no pull
pin27 = Pin(27,Pin.IN)
pin26 = Pin(26,Pin.IN)
adc_solar = machine.ADC(1)
adc_hydro = machine.ADC(0)

pinHydroPower = machine.Pin(22,machine.Pin.OUT)
pinHydroPower.value(1)


time.sleep_ms(10)

if  sw.value() == 0:
    sys.exit()


#DS18B20 declaration. Use specific sensor ID to reduce time (no scan needed).
sensor = (0x28,0x7d,0x38,0x5d,0x4,0x0,0x0,0xad)
#sensor DS18b20 on pin 28
ds = DS18X20(OneWire(machine.Pin(2)))
ds.convert_temp()
# record time in nanosecond
startConv_ms = time.ticks_ms()


#cpu temperature declaration
cpu_temp = machine.ADC(machine.ADC.CORE_TEMP)
conversion_factor = 3.3 / (65535)

def readCpuTemperature():
  reading = cpu_temp.read_u16() * conversion_factor
  return 27 - (reading - 0.706)/0.001721
    
#Vsys Voltage
#N.B. Can't use ADC(29). it crashes!!!!
#to get around it we need to declare ADC(3),
# getPads, setPads, readADC and then put back the original Pads
#set or get GPIO pads settings. Need on Pin29


#def clrPin(gpio):
#    machine.mem32[0xd0000018]=1 << gpio
    
#def setPin(gpio):
#    machine.mem32[0xd0000014]=1 << gpio

def setPad(gpio, value):
    machine.mem32[0x4001c000 | (4+ (4 * gpio))] = value
    
def getPad(gpio):
    return machine.mem32[0x4001c000 | (4+ (4 * gpio))]

def readVsys():
    oldpad = getPad(29)
    setPad(29,128)  #no pulls, no output, no input
    adc_Vsys = machine.ADC(3)
    Vsys = adc_Vsys.read_u16() * 3.0 * conversion_factor
    setPad(29,oldpad)
    return Vsys
    
def readSolar():
    ResistorDivider = 3.12765957447  #470k & 1M   (470K + 1M) / 470K
    Vsolar = adc_solar.read_u16() * ResistorDivider * conversion_factor
    return Vsolar

def readHydro():
    Vhydro = adc_hydro.read_u16() * conversion_factor
    return Vhydro

#network declaration
# Set country to avoid possible errors / https://randomnerdtutorials.com/micropython-mqtt-esp32-esp8266/
rp2.country('CA')

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
# See the MAC address in the wireless chip OTP
#mac = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
#print('mac = ' + mac)


# Load login data from different file for safety reasons

#set static IP
# (IP,mask,gateway,dns)
wlan.ifconfig(('10.11.12.21', '255.255.255.0', '10.11.12.253', '8.8.8.8'))

#connect using ssid


wlan.connect(secrets['ssid'],secrets['pw'])

#set 10 seconds for time out delay
wlandelay =  time.ticks_ms() + 10000


while time.ticks_ms() < wlandelay:
  if wlan.isconnected():
      if wlan.status() <0  or wlan.status() >=3 :
          break
  machine.idle()
   

    
# Handle connection error
# Error meanings
# 0  Link Down
# 1  Link Join
# 2  Link NoIp
# 3  Link Up
# -1 Link Fail
# -2 Link NoNet
# -3 Link BadAuth

if wlan.status() != 3:
    #raise RuntimeError('Wi-Fi connection failed')
    machine.reset()
#else:
    #for i in range(wlan.status()):
    #    led.on()
    #    time.sleep(.1)
    #    led.off()
    #print('Connected')
    #status = wlan.ifconfig()
    #print('ip = ' + status[0])
    
###MQTT  Topic Setup ###

def connectMQTT():
  client = MQTTClient(secrets['client_id'],secrets['broker'])
  client.connect()
  return client


def publish(topic, value):
  #print(topic)
  #print(value)
  pub_msg = "%5.3f" % value
  #print(topic,"  ",pub_msg)
  client.publish(topic, pub_msg)
  #print("publish Done")


try:
  client = connectMQTT()
except OSError as e:
  machine.reset()





def getSensorsAndPublish():
  global vsys
  # record time in nanosecond
  startConv_ms = time.ticks_ms()
  # end need to be 750ms after
  endConv_ms = startConv_ms + 750
  # read cpu Temperature
  publish(secrets['pubtopicTempCPU'],readCpuTemperature())
  # read Vsys
  vsys = readVsys()
  publish(secrets['pubtopicVsys'], vsys)
  # read solar
  publish(secrets['pubtopicVsolar'],readSolar())
  # read Hydro
  publish(secrets['pubtopicVhydro'],readHydro())
  # DS18b20 needs 750ms after conversion
  while time.ticks_ms() < endConv_ms:
      time.sleep_ms(10)
  publish(secrets['pubtopicTemp'], ds.read_temp(sensor))
  
 
#ok main process
  
#Using lightsleep?
  
UsingLightSleep = True
 

try:  
    while True:
        led.value(True)
        time.sleep_ms(100)
        led.value(False)
        getSensorsAndPublish()
        PinHydroPower = machine.Pin(22,Pin.IN)
        time.sleep_ms(750)
        if UsingLightSleep:
            client.disconnect()
            wlan.disconnect()
            wlan.active(False)
            wlan.deinit()
            time.sleep_ms(50)
            if vsys > 4.1 :
                break
            elif vsys > 4.0 :
                machine.lightsleep(50000)
            elif vsys > 3.6:
                machine.lightsleep(110000)
            else:
                machine.lightsleep(290000) # assume 10 sec for connecting
            break
        else:
            time.sleep(10)
except OSError as e:
  pass
machine.reset()
