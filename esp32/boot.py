import network
import webrepl
import machine
from time import sleep
import socket
sta_if = network.WLAN(network.STA_IF)

PIN_ALARM = machine.Pin(12, machine.Pin.OUT)
PIN_LED_RED = machine.Pin(13, machine.Pin.OUT)
PIN_LED_GREEN = machine.Pin(14, machine.Pin.OUT)
PIN_RST = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP)  # Pin for reset button that turns off alarm for 5 minutes

PIN_ALARM.value(0)
PIN_LED_RED.value(0)
PIN_LED_GREEN.value(0)


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

    # Blink green LED 3 times to indicate successful connection to router
    for i in range(0,2):
        sleep(0.1)
        PIN_LED_GREEN.value(1)
        sleep(0.1)
        PIN_LED_GREEN.value(0)

do_connect()
webrepl.start()


def client(host, port):

    print("Connecting to %s:%d..." % (host, port))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    
    print("Connection established.")
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
        print("Alarm turned off locally.")

    PIN_RST.irq(trigger=machine.Pin.IRQ_FALLING, handler=rst_callback)

    while True:
        while doAlarm:
            sock.settimeout(1)
            # Listen for ALARMOFF signal from RPi
            try:
                print("Listening for data...")
                data = sock.recv(512).decode().splitlines()
                if data:
                    print(data)
                if "ALARMOFF" in data:
                    doAlarm = False
                    sock.settimeout(None)
                    print("Alarm turned off by RPi")
                    break
            except:     # MicroPython doesn't like it if we catch socket.timeout specifically
                pass
            PIN_ALARM.value(1)
            PIN_LED_RED.value(1)
            sleep(1)
            PIN_ALARM.value(0)
            PIN_LED_RED.value(0)
            sleep(0.5)

        data = sock.recv(512).decode().splitlines()

        if 'DOALARM' in data:
            doAlarm = True
            print("Alarm triggered!")

        # 'STATUS' should be sent by RPi every 30 seconds.
        # if esp32 fails to respond with 'CONNECTED', RPi sends a phone notification
        elif 'STATUS' in data:
            sock.send('CONNECTED'.encode())
            print("Status OK")

    

    sock.close()
    print("Client closed.")



def main():
    try:
        client('192.168.1.5', 5678)
    except OSError as e:
        print("Connection failed: %s" % e)


main()
