import requests
import time
import RPi.GPIO as GPIO
import socket
import select
import asyncio

GPIO.setmode(GPIO.BCM)

class Server:

    def __init__(self, port):
        self.port = port
        self.PIN_MQ2 = 24
        GPIO.setup(self.PIN_MQ2, GPIO.IN)

        self.MAX_CLIENTS = 1

        # Get IFTTT API key:
        iftttFile = open('ifttt.txt')
        self.IFTTT_KEY = iftttFile.read().strip()
        iftttFile.close()

    def runServer(self):

        print("Starting server on port %d..." % self.port)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('', self.port))
        sock.listen(self.MAX_CLIENTS)
        print("Server started.")

        client, cl_addr = sock.accept()
        client.settimeout(10)
        print("Client %s:%d connected" % cl_addr)
        
        # Ping the esp32 every 30 seconds and wait for a response.
        # Send a push notification if it times out.
        async def getEspStatus(self):
            while True:
                client.send('STATUS'.encode())
                try:
                    data = client.recv(32)
                except socket.timeout:
                    print("Esp32 status query timed out (10 sec), sending push notification...")
                    requests.post('https://maker.ifttt.com/trigger/esp_timeout/with/key/%s' % self.IFTTT_KEY)
                    print("Push notification sent.")
                time.sleep(30)
                
        asyncio.run(getEspStatus(self))

  #      while True:
            # If MQ-2 is low, smoke was detected
   #         if GPIO.input(self.PIN_MQ2) == 0:
                # Send push notification to phone via IFTTT
   #             requests.post('https://maker.ifttt.com/trigger/smoke_detected/with/key/%s' % self.IFTTT_KEY)
                # Send 'DOALARM' to esp32 to trigger the alarm
    #            client.send('DOALARM'.encode())

server = Server(5678)
Server.runServer()