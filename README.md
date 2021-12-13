# FireAlarm

#### A WiFi-enabled fire alarm for use with a Raspberry Pi, ESP32 and MQ-2 smoke detector chip.

**Demonstration:** https://www.youtube.com/watch?v=HQU86N-uDGA

**Explanation:**
I made this to feel safer when leaving my 3D printer running overnight. The Raspberry Pi reads the output pin of an MQ-2 smoke detector chip. When it detects smoke, its output goes to 0 volts. The Raspberry Pi then sets off an alarm connected directly to it, and sets off another alarm via WiFi. That WiFi alarm runs on an ESP32 microcontroller and can be put anywhere in the house, as long as they're both on the same WiFi network.

Directories:
- **/3D files/** -- 3D printable files for the electronics enclosures
- **/esp32/** -- Contains the Python script for the ESP32
- **/gerber/** -- Contains the Gerber files for the circuit board
- **/media/** -- Pictures of the schematics and PCBs
- **/rPi/** -- Contains the Python script for the Raspberry Pi

Raspberry Pi circuit:
![Raspberry Pi circuit](https://user-images.githubusercontent.com/53015970/145156213-e728ce26-c0da-407b-9c1b-d8ddd0ccf781.png)

Raspberry Pi circuit PCB:
![Raspberry Pi circuit PCB](https://user-images.githubusercontent.com/53015970/145156261-f0e5ae24-4825-4fd6-b3a1-95665b763adf.png)

ESP32 circuit:
![ESP32 circuit](https://user-images.githubusercontent.com/53015970/145156298-bced89f1-de96-473b-86e2-d52e9566ce38.png)
