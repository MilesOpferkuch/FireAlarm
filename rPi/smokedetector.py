import requests
import time
import RPi.GPIO as GPIO
import socket
import sys
from multiprocessing import Process

GPIO.setmode(GPIO.BCM)

'''
This script will run on the Raspberry Pi in my garage, which sits next to my 3D printer and runs OctoPrint.
It reads from a MQ-2 smoke detector circuit, which outputs 3.3v normally
but drops to low voltage when there's smoke. This script sets off an alarm in the garage,
and also sends a signal to an ESP32 microprocessor in my bedroom which has its own alarm.
That way I'll hear it if I'm sleeping. In subsequent comments, "local alarm" refers to
the one in the garage and "remote alarm" refers to the one in my bedroom.
'''


class Server:

    def __init__(self, port):
        self.port = port
        self.MAX_CLIENTS = 1

        self.PIN_MQ2 = 24       # Pin from smoke detector DOut
        self.PIN_ALARM = 23     # Pin to enable IC 555 which connects to red LED and piezo alarm
        self.PIN_LED_GREEN = 12
        self.PIN_RST = 25       # Pin to reset button
        GPIO.setup(self.PIN_ALARM, GPIO.OUT)
        GPIO.setup(self.PIN_LED_GREEN, GPIO.OUT)
        GPIO.setup(self.PIN_MQ2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_RST, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.output(self.PIN_ALARM, 0)

        self.alarmIsOn = False
        self.cooldownFlag = False           # Will be set True when RST button pressed. This will disable the alarm for 5 minutes.
        self.cooldownTime = 0.0             # Epoch time when the RST button was last pressed.

        # Get IFTTT API key:
        iftttFile = open('ifttt.txt')
        self.IFTTT_KEY = iftttFile.read().strip()
        iftttFile.close()


    # Pings the esp32 and waits for a response every 30 secs.
    # Sends a push notification if it times out.
    def getEspStatus(self, client):
        self.hasSentTimeoutNotif = False
        print("Started querying ESP32 status.")
        while True:
            client.send('STATUS\n'.encode())  # Ping esp32
            try:
                data = client.recv(32)      # Wait for response
                # If we get a response, reset the notification flag
                if data:
                    print("Received %s from esp32" % data.decode())
                    self.hasSentTimeoutNotif = False
            # If we don't get a response, send push notif if we haven't already done so
            except socket.timeout:  
                if not self.hasSentTimeoutNotif:
                    print("Esp32 status query timed out after 10 seconds, sending push notification...")
            #        requests.post('https://maker.ifttt.com/trigger/esp_timeout/with/key/%s' % self.IFTTT_KEY)
                    self.hasSentTimeoutNotif = True
                    print("Push notification sent.")
                else:
                    print("Esp32 status query timed out after 10 seconds. Already sent push notification.")

            time.sleep(30)


    def alarmOn(self, pin):
        if not self.cooldownFlag:
            GPIO.output(self.PIN_ALARM, 1)
            self.alarmIsOn = True
            print("alarmOn() called")


    def alarmOff(self):
        GPIO.output(self.PIN_ALARM, 0)
        self.alarmIsOn = False
        print("alarmOff() called")


    def main(self):

        # The local alarm is triggered by sys interrupts and runs on a 555 timer
        # to make sure it doesn't get blocked by a network request or something stupid like that.

        # Trigger the local alarm if the MQ2 pin goes low.
        GPIO.add_event_detect(self.PIN_MQ2, GPIO.FALLING, callback=self.alarmOn, bouncetime=100)

        print("Starting server on port %d..." % self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # Fixes "address already in use" error
        sock.bind(('', self.port))
        sock.listen(self.MAX_CLIENTS)
        print("Server started, waiting for client to connect...")

        client, cl_addr = sock.accept()
        client.settimeout(10)
        print("Client %s:%d connected." % cl_addr)

        # Start pinging esp32
        queryProcess = Process(target=self.getEspStatus, args=(client,))
        queryProcess.start()

        while True:

            if (GPIO.input(self.PIN_MQ2) == 0       # If MQ-2 is low, smoke was detected
                and not self.alarmIsOn
                and not self.cooldownFlag):

                self.alarmIsOn = True

                # The local alarm will already be triggered by the system interrupt on the MQ2 pin.
                # This is just for sending the push notification and turning on the esp32's alarm.

                print("Smoke detected! Stopping ESP32 queries...")     
                if queryProcess.is_alive():
                    queryProcess.terminate()

                # Send push notification to phone via IFTTT.
                print("Sending push notification...")
            #    requests.post('https://maker.ifttt.com/trigger/smoke_detected/with/key/%s' % self.IFTTT_KEY)
                print("Notification sent.")

                # Send 'DOALARM' to esp32 to trigger the remote alarm.
                print("Starting remote alarm: Sending signal...")
                client.send('DOALARM\n'.encode())
                print("Signal sent.")

            # Reset cooldown flag 5 minutes after RST button pressed
            if (time.time() >= self.cooldownTime + 300 and self.cooldownFlag):      
                self.cooldownFlag = False
                print("5 minutes since RST pressed. Re-enabling alarm.")

            # Handle RST button press
            if GPIO.input(self.PIN_RST) == 0 and self.alarmIsOn:
                print("Pausing alarm for 5 minutes.")
                self.alarmOff()
                self.cooldownFlag = True
                self.cooldownTime = time.time()
                # Tell esp32 to stop its alarm
                client.send("ALARMOFF\n".encode())
                # Restart esp32 query process
                queryProcess = Process(target=self.getEspStatus, args=(client,))
                queryProcess.start()

            # Turn off alarm if MQ2 goes high again
            if self.alarmIsOn and GPIO.input(self.PIN_MQ2) == 1:
                print("MQ-2 reading high again; turning off alarm.")
                self.alarmOff()
                # Tell esp32 to stop its alarm
                client.send("ALARMOFF\n".encode())

server = Server(5678)
try:
    server.main()
except Exception as e:
    print(e)
    GPIO.cleanup()
    sys.exit(0)