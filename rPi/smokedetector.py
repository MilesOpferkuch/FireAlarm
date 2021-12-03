import requests
import time
import datetime
import RPi.GPIO as GPIO
import socket
import sys
from multiprocessing import Process

GPIO.setmode(GPIO.BCM)

'''
Final project: WiFi smoke detector by Miles Opferkuch

This script will run on a Raspberry Pi in my garage, which sits next to my 3D printer
and runs OctoPrint. It reads from a MQ-2 smoke detector circuit, which normally outputs 3.3v
but drops to low voltage when there's smoke. This script sets off an alarm in the garage,
sends a push notification to my phone, and sends a signal to an ESP32 microprocessor in my bedroom
which has its own alarm. That way I'll hear it if I'm sleeping. In subsequent comments, "local alarm" refers to
the one in the garage (controlled by this script) and "remote alarm" refers to the one in my bedroom (controlled by /esp32/boot.py).
'''



# Print message with local timestamp
def print_t(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzname()
    if tz == "Pacific Standard Time":
        tz = "PST"
    elif tz == "Pacific Daylight Time":
        tz = "PDT"
    print(f'[{timestamp} {tz}] {msg}')



class Server:

    def __init__(self, port):
        self.port = port
        self.alarmIsOn = False
        self.cooldownFlag = False           # Will be set True when RST button pressed. This will disable the alarm for 5 minutes.
        self.cooldownTime = 0.0             # Epoch time when the RST button was last pressed.

        # Get IFTTT API key
        iftttFile = open('ifttt.txt')
        self.IFTTT_KEY = iftttFile.read().strip()
        iftttFile.close()


    # Pings the esp32 and waits for a response every 30 secs.
    # Sends a push notification if it times out. This runs as a subprocess.
    def getEspStatus(self, client):
        try:
            self.hasSentTimeoutNotif = False
            print_t("Started querying ESP32 status.")
            while True:
                client.send('STATUS\n'.encode())  # Ping esp32
                try:
                    data = client.recv(32)      # Wait for response
                    if data:
                        print_t("Received %s from esp32" % data.decode())
                        self.hasSentTimeoutNotif = False    # reset the notification flag
                # If we don't get a response, send push notif if we haven't already done so
                except socket.timeout:  
                    if not self.hasSentTimeoutNotif:
                        print_t("Esp32 status query timed out after 10 seconds, sending push notification...")
                #        requests.post('https://maker.ifttt.com/trigger/esp_timeout/with/key/%s' % self.IFTTT_KEY)
                        self.hasSentTimeoutNotif = True
                        print_t("Push notification sent.")
                    else:
                        print_t("Esp32 status query timed out after 10 seconds. Already sent push notification.")

                time.sleep(30)
        except KeyboardInterrupt:
            GPIO.output(PIN_ALARM, 0)
            GPIO.output(PIN_LED_GREEN, 0)
            GPIO.cleanup()


    # Turn on local alarm
    def alarmOn(self, pin = 0):
        if not self.cooldownFlag:
            GPIO.output(PIN_ALARM, 1)
            self.alarmIsOn = True
            print_t("alarmOn() called!")


    # Turn off local alarm
    def alarmOff(self):
        GPIO.output(PIN_ALARM, 0)
        self.alarmIsOn = False
        print_t("alarmOff() called")


    def main(self):
        # Trigger the local alarm if the MQ2 pin goes low.
        # The local alarm is triggered by pulling PIN_ALARM high.
        # It runs on a 555 timer so we don't block the main thread
        # by turning the buzzer on and off.

        print_t("Starting server on port %d..." % self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # Fixes "address already in use" error
        sock.bind(('', self.port))
        sock.listen(MAX_CLIENTS)
        print_t("Server started, waiting for client to connect...")

        client, cl_addr = sock.accept()
        client.settimeout(10)
        print_t("Client %s:%d connected." % cl_addr)

        for i in range (0, 4):
            GPIO.output(PIN_LED_GREEN, 0)
            time.sleep(0.1)
            GPIO.output(PIN_LED_GREEN, 1)
            time.sleep(0.1)

        # Start pinging esp32
        queryProcess = Process(target=self.getEspStatus, args=(client,))
        queryProcess.start()

        # Main loop
        while True:

            # When smoke detected:
            if (GPIO.input(PIN_MQ2) == 0
                and not self.alarmIsOn
                and not self.cooldownFlag):

                time.sleep(0.25)    # 250ms debounce
                if GPIO.input(PIN_MQ2) == 0:

                    # Trigger local alarm
                    self.alarmIsOn = True
                    self.alarmOn()
                    print_t("Smoke detected! Stopping ESP32 status queries...")
                    if queryProcess.is_alive():
                        queryProcess.terminate()

                    # Send 'DOALARM' to esp32 to trigger the remote alarm.
                    print_t("Starting remote alarm: Sending signal...")
                    client.send('DOALARM\n'.encode())
                    print_t("Signal sent.")

                    # Send push notification to phone via IFTTT.
                    print_t("Sending push notification...")
                #    requests.post('https://maker.ifttt.com/trigger/smoke_detected/with/key/%s' % self.IFTTT_KEY)
                    print_t("Notification sent.")

            # Handle RST button press
            if GPIO.input(PIN_RST) == 0 and self.alarmIsOn:
                print_t("Pausing alarm for 5 minutes.")
                self.alarmOff()
                self.cooldownFlag = True
                self.cooldownTime = time.time()
                # Tell esp32 to stop its alarm
                client.send("ALARMOFF\n".encode())
                # Restart esp32 query process
                queryProcess = Process(target=self.getEspStatus, args=(client,))
                queryProcess.start()

            # Reset cooldown flag 5 minutes after RST button pressed
            if (time.time() >= self.cooldownTime + 300 and self.cooldownFlag):      
                self.cooldownFlag = False
                print_t("5 minutes since RST pressed. Re-enabling alarm.")

            # Turn off alarm if MQ2 goes high again
            if self.alarmIsOn and GPIO.input(PIN_MQ2) == 1:
                print_t("MQ-2 reading high again; turning off alarm.")
                self.alarmOff()
                # Tell esp32 to stop its alarm
                client.send("ALARMOFF\n".encode())


if __name__ == '__main__':
    server = Server(5678)
    MAX_CLIENTS = 1
    PIN_MQ2 = 24
    PIN_ALARM = 23
    PIN_LED_GREEN = 12
    PIN_RST = 25

    GPIO.setup(PIN_ALARM, GPIO.OUT)
    GPIO.setup(PIN_LED_GREEN, GPIO.OUT)
    GPIO.setup(PIN_MQ2, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_RST, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.output(PIN_ALARM, 0)
    GPIO.output(PIN_LED_GREEN, 0)
    try:
        server.main()
    except Exception as e:
        print_t(e)
        GPIO.output(PIN_ALARM, 0)
        GPIO.output(PIN_LED_GREEN, 0)
        GPIO.cleanup()
        sys.exit(0)
    GPIO.cleanup()