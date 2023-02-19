import machine
import rp2
import network
import ubinascii
import time
import sys
from onewire import OneWire
from ds18x20 import DS18X20
from umqtt.simple import MQTTClient
import bme280       #importing BME280 library remark if not used

#umqtt.simple could be imported from Thonny.



#network definition
wifi_essid = "your essid"
wifi_password = "your password"


# define IP,mask and gateway if IP is static
UseStaticIP = True
IP = "10.11.12.22"
IP_mask = "255.255.255.0"
IP_gateway = "10.11.12.253"
IP_DNS = "8.8.8.8"
IP_MQTT_BROKER = "10.11.12.192"

UnitID = "PicoW"

#do we want to use watchdog to reset in case
WatchDog_Enable = True

#sensors definition
#DS18B20 sensors on the same Pin
#more than one sensor could be defined
#if DS18B20Sensors is None then a scan will be done
DS18B20Pin = 2
DS18B20Sensors = [ (0x28,0xff,0x7e,0x74,0xc1,0x17,0x01,0x05) ]
#DS18B20Sensors = [ ( 0x28,0x7d,0x38,0x5d,0x04,0x00,0x00,0xad) ]


#ADC Sensors
#Solar sensor needs
ADC_VoltConversion= 3.3 / (65535)

ADC1_Enable=True
ADC1_PinPower=None
ADC1_Pin=27
ADC1_Topic="Vsolar"
ADC1_CorrectionFactor= 1.0
ADC1_Factor= ADC_VoltConversion * ADC1_CorrectionFactor * 3.12765957447  #470k & 1M   (470K + 1M) / 470K



#moist sensors needs power Pins and ADC 
# two possible moist sensor ADC(0) and ADC(2)
ADC0_Enable=True
ADC0_PinPower=22
ADC0_Pin=26
ADC0_Topic="Vmoist_0"
ADC0_CorrectionFactor= 1.0
ADC0_Factor= ADC_VoltConversion * ADC0_CorrectionFactor

ADC2_Enable=False
ADC2_PinPower=None
ADC2_Pin=28
ADC2_Topic="Vmoist_1"
ADC2_CorrectionFactor= 1.0
ADC2_Factor= ADC_VoltConversion * ADC2_CorrectionFactor


#bme280 sensors
bme_Enable = False
bme_PinSDA=4
bme_PinSCL=5
bme_i2c_address = 0x77
bme_temperature_topic = "bmeT"
bme_pressure_topic = "bmeP"
bme_humidity_topic = "bmeH"

# stop switch  (Press to quit on reset if file is main.py)
switchPin = 19
#ok let's set the Pins
sw = machine.Pin(switchPin,machine.Pin.IN,machine.Pin.PULL_UP)

time.sleep_ms(10)

#On boot do we want to stop main() if yes exit
if  sw.value() == 0:
    sys.exit()


#### WATCH DOG 
# set maximum wachtdog 8.3s  ( 2**24 -1)/2
if WatchDog_Enable:
    wdt = machine.WDT(timeout=8300)

# define lightsleep with watch dog limits
# because we implemented wachtdog we need to
# maximize the light sleep to be lower than 8 second
# the watch dog is 24 bits at 1us clock  by a count of 2
# then the maximum is (2 power 24 -1)/2 which is ~8.3 sec
#  we will use 5 seconds step
def wd_lightsleep(value):
    if WatchDog_Enable:
        while value >0:
            if value >= 5000:
                machine.lightsleep(5000)
                value = value - 5000
            else:
                machine.lightsleep(value)
                value=0
            wdt.feed()
    else:
         machine.lightsleep(value)


#ok let's set the Pins
#i2c
# in bme280 i2c address was 0x76 put adafruit need to be 0x77

if bme_Enable:
    i2c=machine.I2C(0,sda=machine.Pin(bme_PinSDA), scl=machine.Pin(bme_PinSCL), freq=100000)    #initializing the I2C method 
    bme = bme280.BME280(i2c=i2c,address=bme_i2c_address)

#Led
led = machine.Pin('LED', machine.Pin.OUT)

#analog
#first set Pin input no pull first
#moist sensors VCC is on a Pin. we need to set pi High to activate sensor 
# two possible  moist sensor ADC(0) and ADC(2)
#pin object definitioin
ADC0=None
ADC1=None
ADC2=None
ADC0_PWR=None
ADC1_PWR=None
ADC2_PWR=None



if ADC0_Enable:
    #set PIN to INPUT first no pull
    ADC0_IN = machine.Pin(ADC0_Pin,machine.Pin.IN)
    ADC0= machine.ADC(ADC0_Pin -26)

if ADC1_Enable:
    ADC1_IN = machine.Pin(ADC1_Pin,machine.Pin.IN)
    ADC1= machine.ADC(ADC1_Pin -26)

if ADC2_Enable:
    ADC2_IN = machine.Pin(ADC2_Pin,machine.Pin.IN)
    ADC2= machine.ADC(ADC2_Pin -26)

#moist sensor use power So I use a pin to enable disable the sensor
        
def PowerAnalogPin(flag):
    if ADC0_Enable:
        if not (ADC0_PinPower==None):
            if flag:
                ADC0_PWR= machine.Pin(ADC0_PinPower,machine.Pin.OUT)
                ADC0_PWR.value(1)
            else:
                ADC0_PWR= machine.Pin(ADC0_PinPower,machine.Pin.IN)

    if ADC1_Enable:
        if not (ADC1_PinPower==None):
            if flag:
                ADC1_PWR= machine.Pin(ADC1_PinPower,machine.Pin.OUT)
                ADC1_PWR.value(1)
            else:
                ADC1_PWR= machine.Pin(ADC1_PinPower,machine.Pin.IN)
    if ADC2_Enable:
        if not (ADC2_PinPower==None):
            if flag:
                ADC2_PWR= machine.Pin(ADC2_PinPower,machine.Pin.OUT)
                ADC2_PWR.value(1)
            else:
                ADC2_PWR= machine.Pin(ADC2_PinPower,machine.Pin.IN)

#one wire
ds = DS18X20(OneWire(machine.Pin(DS18B20Pin)))

if DS18B20Sensors==None:
    DS18B20Sensors=ds.scan()


#cpu temperature declaration
cpu_temp = machine.ADC(machine.ADC.CORE_TEMP)
conversion_factor = 3.3 / (65535)

def readCpuTemperature():
  reading = cpu_temp.read_u16() * conversion_factor
  return 27 - (reading - 0.706)/0.001721
    

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


def readAnalog(Analog, factor):
    if Analog == None:
        return None
    return Analog.read_u16() * factor

def readBme():
    try:
        t, p, h = bme.read_compensated_data()
        t, p, h = bme.read_compensated_data()
        return (t/100.0 , p/25600.0, h/1024.0)
    except OSError as e:
        pass
    return None    

#network declaration
# Set country to avoid possible errors / https://randomnerdtutorials.com/micropython-mqtt-esp32-esp8266/
rp2.country('CA')
wlan=None
client=None

def stopWifi():
    global client
    global wlan
    if not(client==None):
        client.disconnect()
        client=None
    if not(wlan==None):
        wlan.disconnect()
        wlan.active(False)
        wlan.deinit()
        wlan=None
    time.sleep_ms(100)

def setWifi():
    global wlan
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    # See the MAC address in the wireless chip OTP
    #mac = ubinascii.hexlify(network.WLAN().config('mac'),':').decode()
    #print('mac = ' + mac)
    # Load logimin data from different file for safety reasons
    #set static IP
    # (IP,mask,gateway,dns)
    if UseStaticIP:
        wlan.ifconfig((IP, IP_mask,IP_gateway,IP_DNS))
    wlan.connect(wifi_essid,wifi_password)
    #set 10 seconds for time out delay
    wlandelay =  time.ticks_ms() + 12000
    while time.ticks_ms() < wlandelay:
      if wlan.isconnected():
          if wlan.status() <0  or wlan.status() >=3 :
              break
      machine.idle()
      if WatchDog_Enable:
          wdt.feed()

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
        return False
    return True


def connectWifi():
    for i in range(3):
        #print("connect Client",i)
        if setWifi()==False:
            stopWifi()
            continue
        else:
            return True
    #unable to connect after 3 tentatives
    return False
    
###MQTT  Topic Setup ###

def connectMQTT():
  client = MQTTClient(UnitID,IP_MQTT_BROKER)
  client.connect()
  return client


def publish(topic,value,idx=None):
  global UnitID
  if WatchDog_Enable:
      wdt.feed()
  #print(topic,value)
  pub_msg = "%5.3f" % value
  #print(topic,"  ",pub_msg)
  if idx==None:
      client.publish(UnitID+"/"+topic, pub_msg)
  else:
      client.publish(UnitID+"/"+topic+"_"+str(idx), pub_msg)
  #print("publish Done")



def getSensorsAndPublish():
  global vsys
  
  if not (DS18B20Sensors==None):
      ds.convert_temp()
  # record time in nanosecond
  startConv_ms = time.ticks_ms()
  # end need to be 750ms after
  endConv_ms = startConv_ms + 750
  # read cpu Temperature
  publish('TempCPU',readCpuTemperature())
  # read Vsys
  vsys = readVsys()
  publish('Vsys',vsys)
  # read analog
  
  if ADC0_Enable:
      publish(ADC0_Topic,readAnalog(ADC0,ADC0_Factor))

  if ADC1_Enable:
      publish(ADC1_Topic,readAnalog(ADC1,ADC1_Factor))
  
  if ADC2_Enable:
      publish(ADC2_Topic,readAnalog(ADC2,ADC2_Factor))
 

  
  if bme_Enable:
      v = readBme()

      publish(bme_temperature_topic,v[0])
      publish(bme_pressure_topic,v[1])
      publish(bme_humidity_topic,v[2])

  # DS18b20 needs 750ms after conversion
  while time.ticks_ms() < endConv_ms:
      time.sleep_ms(10)
  for i in range(len(DS18B20Sensors)):
    publish('DS18B20',ds.read_temp(DS18B20Sensors[i]),idx=i)
  
 
#ok main process
 

try:  
    while True:
        PowerAnalogPin(True)
        try:
            if not connectWifi():
                #print("wifi connect Failed restart")
                time.sleep_ms(500)
                machine.reset()
            client = connectMQTT()
        except OSError as e:
            #print("WIFI OR MQTT Failed restart")
            time.sleep_ms(500)
            machine.reset()
        led.value(True)
        time.sleep_ms(100)
        led.value(False)
        getSensorsAndPublish()
        # turn analog PWR PIN OFF
        PowerAnalogPin(False)
        time.sleep_ms(750)
        stopWifi()
        time.sleep_ms(50)
        # depending of Voltage in battery cycle will differ
        # at 4.1V do 30 sec cycle this will draw more power than solar
        if vsys > 4.1 :
            wd_lightsleep(21600)  #30 sec cycle
        elif vsys > 4.0 :
            wd_lightsleep(51600)  #60 sec cycle
        elif vsys > 3.6:
            wd_lightsleep(111600) #120 sec cycle
        else:
            wd_lightsleep(291600) #5 min cycle
except OSError as e:
    #print("OS ERROR restart")
    time.sleep_ms(500)
    machine.reset()
