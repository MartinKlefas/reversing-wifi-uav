Sniffing the Drone "Connection Boot" Packet on Linux (Monitor Mode)
===================================================================

Some drones seem to have some extra controls, one of which is a mandatory "Connection Boot" package at the start of a session sometimes present. These instructions describe how to **passively capture** the UDP "connection boot" (handshake) packet sent by a mobile app to a toy Wi-Fi drone, **without connecting a second client to the drone's Wi-Fi network**.

This avoids triggering drones that only allow a **single associated Wi-Fi client**.

* * * * *

Overview
--------

The drone operates as a Wi-Fi Access Point (AP) and expects exactly one connected client (the mobile app). When a second device associates, the app reports an error and the drone refuses control.

To observe the handshake safely:

-   The **phone** connects normally to the drone Wi-Fi

-   The **Linux machine** does **not** associate to the drone

-   The Linux machine places its wireless interface into **monitor mode**

-   All packets are captured passively from the air

* * * * *

Requirements
------------

### Hardware

-   Linux machine with:

    -   One **wired Ethernet interface** (for internet access)

    -   One **wireless interface** that supports **monitor mode**

-   Smartphone with the official drone control app

-   Drone powered on and advertising its Wi-Fi network

> ⚠️ Many internal laptop Wi-Fi adapters support monitor mode, but not all.\
> USB adapters based on Atheros or Realtek chipsets usually work well.

* * * * *

Software
--------

Install the required tools:

`sudo apt update
sudo apt install wireshark aircrack-ng`

During the Wireshark installation, **allow** non-superusers to capture packets.

Add your user to the Wireshark group:

`sudo usermod -aG wireshark $USER`

Log out and log back in for group membership to take effect.

* * * * *

Procedure
---------

### 1\. Identify the Wireless Interface

List network interfaces:

`ip link`

Identify your wireless interface (commonly `wlan0`, `wlp3s0`, etc.).\
In the examples below, `wlan0` is used.

* * * * *

### 2\. Stop Conflicting Services

Disable services that interfere with monitor mode:

`sudo airmon-ng check kill`

This will temporarily stop NetworkManager and wpa_supplicant.\
Your **wired Ethernet connection remains active**.

* * * * *

### 3\. Enable Monitor Mode

Put the wireless interface into monitor mode:

`sudo airmon-ng start wlan0`

Expected output:

`monitor mode enabled on wlan0mon`

The monitor interface will typically be named `wlan0mon`.

* * * * *

### 4\. Discover the Drone Wi-Fi Channel

Scan nearby Wi-Fi networks:

`sudo airodump-ng wlan0mon`

Wait until the drone's SSID appears (e.g. `WIFI-UAV_XXXX`) and note the **channel number**.

Example:

`WIFI-UAV_1234   ch 6`

Stop the scan with **Ctrl+C**.

* * * * *

### 5\. Start a Focused Capture

Capture traffic only on the drone's channel:

`sudo airodump-ng -c 6 -w drone_boot wlan0mon`

Replace `6` with the actual channel number.

This will create a capture file:

`drone_boot-01.cap`

* * * * *

### 6\. Trigger the "Connection Boot" in the App

While the capture is running:

1.  Power on the drone

2.  Connect the phone to the drone's Wi-Fi

3.  Open the drone control app

4.  Press **"connection boot"**

5.  Wait 2--3 seconds

6.  Stop the capture with **Ctrl+C**

* * * * *

### 7\. Analyze the Capture in Wireshark

Open the capture file:

`wireshark drone_boot-01.cap`

Apply a display filter:

`udp`

Then narrow further if needed:

`udp.port == 8800`

* * * * *

Identifying the Boot Packet
---------------------------

The "connection boot" packet is typically:

-   A **single or very small number of UDP packets**

-   Sent **only once**

-   Often **shorter** than regular control packets

-   Sent immediately before the drone transitions to an active state (LEDs stop flashing)

In contrast, control packets:

-   Are usually fixed-length (e.g. 20 bytes)

-   Repeat continuously at high frequency

To confirm:

-   Capture once **without** pressing "connection boot"

-   Capture once **with** pressing it

-   Compare the two captures and isolate the difference

* * * * *

Restoring Normal Wi-Fi Operation
--------------------------------

After capturing:

`sudo airmon-ng stop wlan0mon
sudo systemctl restart NetworkManager`

Your wireless networking will return to normal operation.

* * * * *

Outcome
-------

At the end of this process, you should have identified the **exact UDP payload** sent by the app during the connection boot phase. This packet can then be reproduced programmatically (e.g. in Python) to initialise the drone without using the mobile app.

* * * * *

Notes
-----

-   Monitor mode is **passive**; the drone is unaware of the Linux machine

-   This method avoids triggering single-client restrictions

-   No modification of the drone or mobile app is required