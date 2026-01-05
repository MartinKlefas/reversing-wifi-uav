Recording and validating movement commands (longer sessions)
------------------------------------------------------------

### Goal

Capture a longer flight session and verify that:

-   Control packets are consistently sent to the expected UDP port (commonly `8800`)

-   Packet format matches the expected "RC frame" structure

-   Specific stick movements map to predictable byte changes (roll/pitch/throttle/yaw)

-   Special commands (takeoff/land/emergency/calibrate) appear as distinct command bytes

This is helpful if:

-   The library "works sometimes" and you suspect a missing handshake or different packet variant

-   You want to confirm byte positions and neutral values for *your* drone model

-   You want to build a reliable Python controller and regression-test it

* * * * *

### Prerequisites

-   Linux machine with a wireless adapter supporting monitor mode

-   `aircrack-ng`, `wireshark` installed (as per the earlier boot sniffing guide)

Optional but recommended for cleaner captures:

-   `tshark` (comes with Wireshark on most distros)

Install if needed:

`sudo apt update
sudo apt install wireshark aircrack-ng`

* * * * *

### 1) Enable monitor mode (passive sniffing)

Identify your wireless interface (example uses `wlan0`):

`ip link`

Stop interfering services:

`sudo airmon-ng check kill`

Enable monitor mode:

`sudo airmon-ng start wlan0`

You'll typically get `wlan0mon`.

* * * * *

### 2) Find the drone Wi-Fi channel

Scan for the drone SSID:

`sudo airodump-ng wlan0mon`

Note the channel (e.g. `6`). Stop with Ctrl+C.

* * * * *

### 3) Capture a longer session

You have two good options:

#### Option A (recommended): capture with `tshark` (straight to PCAP)

This tends to produce files that are easiest to parse programmatically.

`sudo tshark -I -i wlan0mon -f "wlan type data" -w session.pcap`

-   `-I` = monitor mode capture

-   `-f "wlan type data"` filters to data frames (less clutter)

Let it run.

Now:

1.  Connect phone to drone Wi-Fi

2.  Open app

3.  Press "connection boot"

4.  Fly a short, deliberate script of movements (see below)

5.  Stop capture with Ctrl+C

#### Option B: capture with `airodump-ng`

`sudo airodump-ng -c 6 -w session wlan0mon`

This produces `session-01.cap` which is also usable, but `tshark` → `.pcap` is often smoother.

* * * * *

### 4) Fly a "deliberate" validation script (human-operated)

To make analysis easy, do obvious moves with pauses:

1.  Boot/arm (press "connection boot")

2.  **Takeoff** (if app has it)

3.  Hover 2 seconds

4.  Push **forward** 1 second, neutral 2 seconds

5.  Push **forward** 1 second again, neutral 2 seconds

6.  Push **right** 1 second, neutral 2 seconds

7.  **Yaw left** 1 second, neutral 2 seconds

8.  Increase **throttle** 1 second, neutral 2 seconds

9.  **Land**

This creates clear "events" you can count (`forward x2`, etc.).

* * * * *

### 5) Analyse in Wireshark (manual sanity check)

Open `session.pcap` in Wireshark and filter:

-   All UDP:

    `udp`

-   If you expect control port 8800:

    `udp.port == 8800`

Pick a packet and inspect payload bytes. For many toy drones, a control frame often:

-   starts with `0x66`

-   ends with `0x99`

-   contains four "RC" bytes with a neutral of around `0x80`

-   includes a "command byte" for takeoff/land/emergency/calibrate

* * * * *

Python: Parse a capture and infer commands/events
-------------------------------------------------

This script reads a `.pcap` (recommended) and:

-   extracts UDP payloads (default port `8800`)

-   detects "RC frames" with:

    -   start byte `0x66`

    -   end byte `0x99`

    -   RC channels near `0x80` neutral

-   converts channel deviations into:

    -   forward/back

    -   left/right

    -   up/down (throttle)

    -   yaw left/right

-   counts **events** using a simple debouncer (so continuous stick hold doesn't count 50 times)

### Install dependency

This script uses **Scapy**:

`python3 -m pip install scapy`

Usage examples
--------------

### 1) Basic run

`python3 tools/pcap_decode.py session.pcap`

### 2) If your port differs

`python3 tools/pcap_decode.py session.pcap --port 9000`

### 3) Print a few decoded frames to confirm offsets & neutral

`python3 tools/pcap_decode.py session.pcap --show-first 20`

### 4) If you get too many "events" due to jitter

Increase deadband and/or debounce:

`python3 tools/pcap_decode.py session.pcap --deadband 20 --debounce 1.0`

* * * * *

Notes and limitations
---------------------

-   **Axis direction may be inverted** depending on your drone/app mapping.\
    If "forward" is being detected when you pull back, swap labels in `infer_event()`.

-   This script assumes the capture contains **decoded IP/UDP** packets.\
    That's why capturing with `tshark -I ... -w session.pcap` is recommended.

-   Some drones embed control in non-IP 802.11 payloads; if you suspect that, we can extend the parser to decode raw 802.11 frames.