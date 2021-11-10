import requests
import time
import RPi.GPIO as GPIO
import socket
import select
import asyncio



class Server:

    def __init__(self):
        GPIO.setmode(GPIO.BCM)

        self.PIN_MQ2 = 24
        GPIO.setup(self.PIN_MQ2, GPIO.IN)

        iftttFile = open('ifttt.txt')
        self.IFTTT_KEY = iftttFile.read().strip()
        iftttFile.close()

    def runServer(self, port):

        print("Starting server on port %d..." % port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', port))
        sock.listen(1)      # param here is max clients
        print("Server started.")

        client, cl_addr = sock.accept()
        client.settimeout(10)
        print("Client %s:%d connected" % cl_addr)
        
        # Ping the esp32 every 30 seconds and wait for a response.
        # Send a push notification if it times out.
        async def getEspStatus():
            while True:
                client.send('STATUS')
                try:
                    data = client.recv(32)
                except socket.timeout:
                    print("Esp32 status query timed out (10 sec), sending push notification...")
                    requests.post('https://maker.ifttt.com/trigger/esp_timeout/with/key/%s' % self.IFTTT_KEY)
                    print("Push notification sent.")
                time.sleep(30)
                
        asyncio.run(getEspStatus)



        while True:
            # If MQ-2 is low, smoke was detected
            if GPIO.input(self.PIN_MQ2) == 0:
                # Send push notification to phone via IFTTT
                requests.post('https://maker.ifttt.com/trigger/smoke_detected/with/key/%s' % self.IFTTT_KEY)
                # Send 'DOALARM' to esp32 to trigger the alarm
                client.send('DOALARM'.encode())
