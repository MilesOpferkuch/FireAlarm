import requests
import time
import RPi.GPIO as GPIO
import socket
import sys
from multiprocessing import Process

GPIO.setmode(GPIO.BCM)



class Server:

    def __init__(self, port):
        self.port = port
        self.MAX_CLIENTS = 1

        self.PIN_LED = 18       # Pin to status LED
        self.PIN_ALARM = 23     # Pin to piezo alarm
        self.PIN_MQ2 = 24       # Pin to smoke detector DOut
        self.PIN_RST = 25       # Pin to reset button
        GPIO.setup(self.PIN_LED, GPIO.OUT)
        GPIO.setup(self.PIN_ALARM, GPIO.OUT)
        GPIO.setup(self.PIN_MQ2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.PIN_RST, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.alarmOn = False
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
        while True:
            print("getEspStatus() called")
            client.send('STATUS'.encode())  # Ping esp32

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

            time.sleep(15)


    # Sets off piezo alarm and LED connected to RPi
    def doAlarm(self):
        while True:
            print("wee woo wee woo")
            GPIO.output(self.PIN_ALARM, 1)
            GPIO.output(self.PIN_LED, 1)
            time.sleep(1)
            GPIO.output(self.PIN_ALARM, 0)
            GPIO.output(self.PIN_LED, 0)
            time.sleep(1)


    def main(self):
        print("Starting server on port %d..." % self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # Fixes "address already in use" error
        sock.bind(('', self.port))
        sock.listen(self.MAX_CLIENTS)
        print("Server started.")

        client, cl_addr = sock.accept()
        client.settimeout(10)
        print("Client %s:%d connected" % cl_addr)

        queryProcess = Process(target=self.getEspStatus, args=(client,))
        queryProcess.start()

        while True:
            if (GPIO.input(self.PIN_MQ2) == 0       # If MQ-2 is low, smoke was detected
                and not self.alarmOn
                and not self.cooldownFlag):

                # Trip alarm and disable esp32 status queries
                print("Smoke detected! Starting local alarm...")
                self.alarmOn = True      
                alarmProcess = Process(target=self.doAlarm)
                alarmProcess.start()
                if queryProcess.is_alive():
                    queryProcess.terminate()

                # Send push notification to phone via IFTTT
                print("Sending push notification...")
            #    requests.post('https://maker.ifttt.com/trigger/smoke_detected/with/key/%s' % self.IFTTT_KEY)
                print("Notification sent.")

                # Send 'DOALARM' to esp32 to trigger the remote alarm
                print("Starting remote alarm: Sending signal...")
                client.send('DOALARM'.encode())
                print("Signal sent.")

            # Reset cooldown flag 5 minutes after RST button pressed
            if (time.time() >= self.cooldownTime + 300 and self.cooldownFlag):      
                self.cooldownFlag = False
                print("5 minutes since RST pressed. Re-enabling alarm.")

            # Handle RST button press
            if GPIO.input(self.PIN_RST) == 0 and self.alarmOn:
                print("Pausing alarm for 5 minutes.")
                self.alarmOn = False
                if alarmProcess.is_alive():
                    alarmProcess.terminate()
                self.cooldownFlag = True
                self.cooldownTime = time.time()
                GPIO.output(self.PIN_ALARM, 0)
                GPIO.output(self.PIN_LED, 0)
                # Tell esp32 to stop the alarm
                client.send("ALARMOFF".encode())
                # Restart esp32 query process
                queryProcess = Process(target=self.getEspStatus, args=(client,))
                queryProcess.start()



server = Server(5678)
try:
    server.main()
except KeyboardInterrupt:
    GPIO.cleanup()
    sys.exit(0)