import network
import webrepl
import machine
import errno
import time
from time import localtime
from ntptime import settime
import socket
import urequests

'''
Final project: WiFi smoke detector by Miles Opferkuch
https://github.com/MilesOpferkuch/FireAlarm

This script runs on the ESP32 microprocessor in my bedroom. It receives data
from the Raspberry Pi in my garage, and sets off an alarm when it receives the signal to do so.
Note that this uses Micropython and will only run on an ESP32 (or possibly an ESP8266).
It's also specific to how my circuit is wired: https://github.com/MilesOpferkuch/FireAlarm/blob/main/media/ESP32_schem.png
'''


# Set up GPIO pins
PIN_ALARM = machine.Pin(15, machine.Pin.OUT)                   # Pin to piezo buzzer
PIN_LED_RED = machine.Pin(2, machine.Pin.OUT)                  # Pin to red status light
PIN_LED_GREEN = machine.Pin(0, machine.Pin.OUT)                # Pin to green status light
PIN_RST = machine.Pin(5, machine.Pin.IN, machine.Pin.PULL_UP)  # Pin to reset button

# Pull low on startup
PIN_ALARM.value(0)
PIN_LED_RED.value(0)
PIN_LED_GREEN.value(0)

# The time we last received a ping from RPi.
# If this exceeds 40 seconds, the connection is dead and we send a push notification.
lastPingTime = 0.0

hasSentPushNotif = False

# Get IFTTT API key
iftttFile = open('ifttt.txt')
IFTTT_KEY = iftttFile.read().strip()
iftttFile.close()

# Get WiFi credentials
credfile = open('wifi.txt')
SSID, PWD = str.splitlines(credfile.read())
credfile.close()

# Prints messages with a UTC timestamp. Micropython lacks a lot of
# Python's datetime formatting stuff so we have to do it manually.
def print_t(msg):
    # localtime() returns a tuple so I convert it to a list for formatting.
    # Despite the name, it's actually in UTC.
    time = list(localtime())
    # Zero-padding
    for i in range (0, len(time)):
        if len(time[i]) == 1:
            time[i] = "0" + time[i]
    # [yyyy-MM-dd HH:mm:ss UTC]
    print(f'[{time[0]}-{time[1]}-{time[2]} {time[3]}:{time[4]}:{time[5]} UTC] {msg}')


# Make error codes human-readable
def errorName(e):
    errorName = "???"
    try:
        errorName = errno.errorcode[e.errno]
    except:
        pass
    return errorName


# Connect to WiFi
def wifi_connect():
    sta_if = network.WLAN(network.STA_IF)
    if not sta_if.isconnected():
        print('Connecting to network %s...' % SSID)
        sta_if.active(True)
        sta_if.connect(SSID, PWD)
        while not sta_if.isconnected():
            PIN_LED_RED.value(1)
            PIN_LED_GREEN.value(1)
            pass
    print('Connected to WiFi. Network config:', sta_if.ifconfig())

    # Set clock
    try:
        settime()
    except OSError:
        print("Error getting time from remote server. Log timestamps will be incorrect.")
    rtc = machine.RTC()
    print_t("System clock set.")

    PIN_LED_RED.value(0)
    # Blink green LED to indicate successful connection to router
    for i in range(0,4):
        time.sleep(0.2)
        PIN_LED_GREEN.value(1)
        time.sleep(0.2)
        PIN_LED_GREEN.value(0)

isConnectedToWifi = False
try:
    wifi_connect()
    isConnectedToWifi = True
except OSError as e:
    PIN_LED_RED.value(1)
    print(f"Could not connect to {SSID}: error code {str(e.errno)} [{errorName(e)}].\nTrying again in 5 seconds.")

webrepl.start()

# Connect to RPi and retry if it fails
def server_connect(host, port):
    isConnectedToPi = False
    while not isConnectedToPi:
        try:
            print_t("Connecting to %s:%d..." % (host, port))
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((host, port))
            isConnectedToPi = True
        except OSError as e:
            sock.close()
            PIN_LED_RED.value(1)
            print_t(f"Connection to RPi failed: error code {str(e.errno)} [{errorName(e)}].\nTrying again in 5 seconds.")
            time.sleep(5)
    print_t("Connection established.")
    PIN_LED_RED.value(0)
    PIN_LED_GREEN.value(1)
    return sock

# Set up client
def client(host, port):

    doAlarm = False
    sock = server_connect(host, port)

    # Callback for reset button IRQ
    def rst_callback(pin):
        nonlocal doAlarm
        doAlarm = False
        PIN_LED_RED.value(0)
        PIN_ALARM.value(0)
        print_t("Reset button pressed. Local alarm turned off.")

    # Set up CPU interrupt for reset button.
    # This is on an interrupt so it works even while the thread is blocked.
    PIN_RST.irq(trigger=machine.Pin.IRQ_FALLING, handler=rst_callback)

    # Main loop
    while True:

        data = sock.recv(512).decode().splitlines()     # Listen for data from RPi

        # Fire the alarm if we get the signal from RPi
        if 'DOALARM' in data:
            print_t("Alarm triggered!")
            sock.settimeout(1)
            doAlarm = True
            while doAlarm:
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
                # Blink LED and buzzer
                PIN_ALARM.value(1)
                PIN_LED_RED.value(1)
                time.sleep(1)
                PIN_ALARM.value(0)
                PIN_LED_RED.value(0)
                # No need to sleep here, the network timeout is 1 second

        # 'STATUS' should be sent by RPi every 30 seconds.
        # if esp32 fails to respond with 'CONNECTED', RPi sends a phone notification.
        if 'STATUS' in data:
            lastPingTime = time.time()
            hasSentPushNotif = False
            sock.send('CONNECTED'.encode())
            print_t("Status OK")
            PIN_LED_GREEN.value(1)
            PIN_LED_RED.value(0)

        # Send notification if 40 seconds have passed since the last ping from RPi
        if (time.time() > lastPingTime + 40 and not hasSentPushNotif):
            PIN_LED_RED.value(1)
            print_t("Lost connection to RPi! Sending push notification...")
            notif = urequests.post('https://maker.ifttt.com/trigger/rpi_timeout/with/key/%s' % IFTTT_KEY)
            notif.close()
            print_t("Push notification sent.")
            hasSentPushNotif = True

            sock.close()    # Close the old socket
            sock = server_connect(host, port)   # Try to make a new one

    sock.close()
    print_t("Client closed.")



def main():
    try:
        client('192.168.1.16', 5678)  # my RPi server is running on this IP
    except OSError as e:
        print(f"Connection to RPi failed: error code {str(e.errno)} [{errorName(e)}]")
        PIN_LED_RED.value(1)
        PIN_LED_GREEN.value(0)
    except KeyboardInterrupt:
        PIN_LED_RED.value(0)
        PIN_LED_GREEN.value(0)

main()