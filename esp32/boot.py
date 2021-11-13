import network
import webrepl
import machine
import time
from time import localtime
from ntptime import settime
import socket

sta_if = network.WLAN(network.STA_IF)

PIN_ALARM = machine.Pin(15, machine.Pin.OUT)
PIN_LED_RED = machine.Pin(2, machine.Pin.OUT)
PIN_LED_GREEN = machine.Pin(0, machine.Pin.OUT)
PIN_RST = machine.Pin(4, machine.Pin.IN, machine.Pin.PULL_UP)  # Pin for reset button that turns off alarm for 5 minutes

PIN_ALARM.value(0)
PIN_LED_RED.value(0)
PIN_LED_GREEN.value(0)

'''
This script runs on the ESP32 microprocessor in my bedroom. It receives data
from the Raspberry Pi in my garage, and sets off an alarm if it receives the signal to do so.
'''

# Print message with UTC timestamp
def print_t(msg):
    time = localtime()  # "localtime" on MicroPython is actually UTC
    timelist = []
    # zero-padding
    for i in time:
        timelist.append(str(i))
    for i in range (0, len(timelist)):
        if len(timelist[i]) == 1:
            timelist[i] = "0" + timelist[i]

    print(f'[{timelist[0]}-{timelist[1]}-{timelist[2]} {timelist[3]}:{timelist[4]}:{timelist[5]} UTC] {msg}')


# Connect to WiFi
def do_connect():

    credfile = open('wifi.txt')
    wificreds = str.splitlines(credfile.read())
    ssid, pwd = wificreds
    credfile.close()

    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network %s...' % ssid)
        sta_if.active(True)
        sta_if.connect(ssid, pwd)
        while not sta_if.isconnected():
            PIN_LED_RED.value(1)
            PIN_LED_GREEN.value(0)
            pass
    print('network config:', sta_if.ifconfig())

    # Set RTC
    settime()
    rtc = machine.RTC()
    print_t("System clock set.")

    PIN_LED_RED.value(0)
    # Blink green LED to indicate successful connection to router
    for i in range(0,4):
        time.sleep(0.1)
        PIN_LED_GREEN.value(1)
        time.sleep(0.1)
        PIN_LED_GREEN.value(0)
    

do_connect()
webrepl.start()


def client(host, port):

    print_t("Connecting to %s:%d..." % (host, port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    
    print_t("Connection established.")
    # Connected to RPi server: solid green light and no red light 
    PIN_LED_RED.value(0)
    PIN_LED_GREEN.value(1)

    doAlarm = False

    # Set up interrupt for reset button
    def rst_callback(pin):
        nonlocal doAlarm
        doAlarm = False
        PIN_LED_RED.value(0)
        PIN_ALARM.value(0)
        print_t("Alarm turned off locally.")

    PIN_RST.irq(trigger=machine.Pin.IRQ_FALLING, handler=rst_callback)

    while True:

        while doAlarm:
            sock.settimeout(1)
            # Listen for ALARMOFF signal from RPi
            try:
                print_t("Listening for data...")
                data = sock.recv(512).decode().splitlines()
                if "ALARMOFF" in data:
                    doAlarm = False
                    sock.settimeout(None)
                    print_t("Alarm turned off by RPi")
                    break
            except:     # MicroPython doesn't like it if we catch socket.timeout specifically
                pass
            PIN_ALARM.value(1)
            PIN_LED_RED.value(1)
            time.sleep(1)
            PIN_ALARM.value(0)
            PIN_LED_RED.value(0)
            time.sleep(0.5)

        data = sock.recv(512).decode().splitlines()

        if 'DOALARM' in data:
            doAlarm = True
            print_t("Alarm triggered!")

        # 'STATUS' should be sent by RPi every 30 seconds.
        # if esp32 fails to respond with 'CONNECTED', RPi sends a phone notification.
        elif 'STATUS' in data:
            sock.send('CONNECTED'.encode())
            print_t("Status OK")


    sock.close()
    print_t("Client closed.")



def main():
    try:
        client('192.168.1.5', 5678)
    except OSError as e:
        print("Connection failed: %s" % e)


main()