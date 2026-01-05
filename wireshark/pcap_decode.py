#!/usr/bin/env python3
"""
Decode toy-drone UDP control frames from a packet capture and infer high-level events.

Assumptions (based on common "WIFI-UAV" style drones):
- UDP control frames are sent to a known port (default: 8800)
- A control frame is 20 bytes:
    [0]  = 0x66 (start)
    [2:6] = roll, pitch, throttle, yaw (0x00..0xFF), neutral near 0x80
    [6]  = command byte (e.g., takeoff/land/etc.)
    [7]  = headless mode byte
    [18] = checksum (often XOR of bytes 2..7; not enforced here)
    [19] = 0x99 (end)
These offsets match the description you posted, but you can adjust them if your captures differ.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from scapy.all import PcapReader  # type: ignore
from scapy.layers.inet import IP, UDP  # type: ignore


NEUTRAL = 0x80

# How far away from NEUTRAL before we consider it a "movement"
DEFAULT_DEADBAND = 12  # tweak if your sticks are noisy

# Minimum time between counting the same event again (seconds)
DEFAULT_DEBOUNCE = 0.60

# Some common command byte mappings (adjust if your drone differs)
COMMANDS = {
    0x00: "none",
    0x01: "takeoff",
    0x02: "emergency_stop",
    0x03: "land",
    0x04: "calibrate_gyro",
}


@dataclass
class RCFrame:
    ts: float
    roll: int
    pitch: int
    throttle: int
    yaw: int
    cmd: int
    headless: int
    raw: bytes


def is_candidate_rc_frame(payload: bytes) -> bool:
    return (
        len(payload) == 20
        and payload[0] == 0x66
        and payload[-1] == 0x99
    )


def parse_rc_frame(ts: float, payload: bytes) -> Optional[RCFrame]:
    if not is_candidate_rc_frame(payload):
        return None

    # Offsets based on your description: 3rd..6th bytes are RC values -> indices 2..5
    roll = payload[2]
    pitch = payload[3]
    throttle = payload[4]
    yaw = payload[5]
    cmd = payload[6]
    headless = payload[7]

    return RCFrame(
        ts=ts,
        roll=roll,
        pitch=pitch,
        throttle=throttle,
        yaw=yaw,
        cmd=cmd,
        headless=headless,
        raw=payload,
    )


def classify_axis(value: int, neutral: int, deadband: int, pos_label: str, neg_label: str) -> Optional[str]:
    delta = value - neutral
    if abs(delta) <= deadband:
        return None
    return pos_label if delta > 0 else neg_label


def infer_event(frame: RCFrame, deadband: int) -> List[str]:
    """
    Turn a single RC frame into zero or more "instantaneous" labels.
    We later debounce these into counted events.
    """
    events: List[str] = []

    # Special command byte
    if frame.cmd in COMMANDS and COMMANDS[frame.cmd] != "none":
        events.append(COMMANDS[frame.cmd])
    elif frame.cmd != 0x00:
        events.append(f"cmd_0x{frame.cmd:02x}")

    # Axis movements (naming may need flipping depending on your drone)
    # NOTE: many drones map pitch+ as forward, roll+ as right; some are inverted.
    pitch_evt = classify_axis(frame.pitch, NEUTRAL, deadband, "forward", "back")
    roll_evt = classify_axis(frame.roll, NEUTRAL, deadband, "right", "left")
    thr_evt = classify_axis(frame.throttle, NEUTRAL, deadband, "up", "down")
    yaw_evt = classify_axis(frame.yaw, NEUTRAL, deadband, "yaw_right", "yaw_left")

    for e in (pitch_evt, roll_evt, thr_evt, yaw_evt):
        if e:
            events.append(e)

    # Headless mode byte (optional)
    if frame.headless not in (0x00, 0x02, 0x03):  # common: 0x02 off, 0x03 on
        events.append(f"headless_0x{frame.headless:02x}")
    elif frame.headless == 0x03:
        events.append("headless_on")
    elif frame.headless == 0x02:
        events.append("headless_off")

    return events


def debounce_and_count(events_over_time: List[Tuple[float, str]], debounce_s: float) -> Dict[str, int]:
    """
    Count events, preventing rapid repeats. If an event label repeats within debounce_s,
    it is considered the same continuous action and not counted again.
    """
    counts: Dict[str, int] = {}
    last_seen: Dict[str, float] = {}

    for ts, label in events_over_time:
        prev = last_seen.get(label)
        if prev is None or (ts - prev) >= debounce_s:
            counts[label] = counts.get(label, 0) + 1
            last_seen[label] = ts
        else:
            # within debounce window -> ignore
            continue

    return counts


def extract_udp_payloads(pcap_path: str, dport: int) -> Iterable[Tuple[float, bytes]]:
    """
    Yield (timestamp, UDP payload) from a PCAP. This expects IP/UDP packets to be present.
    If you capture only 802.11 frames without radiotap->IP decode, ensure you're saving as PCAP
    via tshark as recommended in the capture instructions.
    """
    with PcapReader(pcap_path) as pcap:
        for pkt in pcap:
            # Scapy timestamps are on the packet
            ts = float(getattr(pkt, "time", 0.0))

            if IP in pkt and UDP in pkt:
                udp = pkt[UDP]
                if int(udp.dport) == dport or int(udp.sport) == dport:
                    payload = bytes(udp.payload)
                    if payload:
                        yield ts, payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Infer drone commands from a PCAP capture.")
    ap.add_argument("pcap", help="Path to capture file (prefer .pcap from tshark)")
    ap.add_argument("--port", type=int, default=8800, help="UDP control port (default: 8800)")
    ap.add_argument("--deadband", type=int, default=DEFAULT_DEADBAND, help="Neutral deadband threshold")
    ap.add_argument("--debounce", type=float, default=DEFAULT_DEBOUNCE, help="Debounce time in seconds")
    ap.add_argument("--max", type=int, default=0, help="Max frames to parse (0 = no limit)")
    ap.add_argument("--show-first", type=int, default=0, help="Print first N decoded frames for debugging")
    args = ap.parse_args()

    frames: List[RCFrame] = []
    decoded = 0

    for ts, payload in extract_udp_payloads(args.pcap, args.port):
        f = parse_rc_frame(ts, payload)
        if not f:
            continue
        frames.append(f)
        decoded += 1
        if args.max and decoded >= args.max:
            break

    if not frames:
        print("No RC frames found.")
        print("Tips:")
        print("- Confirm capture contains IP/UDP packets (recommend capturing with: tshark -I -i wlan0mon ... -w session.pcap)")
        print("- Try changing --port if your drone uses a different port")
        return 2

    if args.show_first:
        print(f"First {min(args.show_first, len(frames))} frames:")
        for f in frames[: args.show_first]:
            print(
                f"t={f.ts:.3f} roll={f.roll:3d} pitch={f.pitch:3d} thr={f.throttle:3d} yaw={f.yaw:3d} "
                f"cmd=0x{f.cmd:02x} headless=0x{f.headless:02x} raw={f.raw.hex()}"
            )
        print()

    # Convert frames to event stream
    event_stream: List[Tuple[float, str]] = []
    for f in frames:
        labels = infer_event(f, args.deadband)
        for label in labels:
            event_stream.append((f.ts, label))

    counts = debounce_and_count(event_stream, args.debounce)

    # Print summary
    print(f"Decoded RC frames: {len(frames)}")
    print(f"UDP port: {args.port}")
    print(f"Deadband: ±{args.deadband} around {NEUTRAL} (0x{NEUTRAL:02x})")
    print(f"Debounce: {args.debounce:.2f}s")
    print()

    # Nice ordering: commands first, then axes
    preferred_order = [
        "takeoff", "land", "emergency_stop", "calibrate_gyro",
        "forward", "back", "left", "right", "up", "down", "yaw_left", "yaw_right",
        "headless_on", "headless_off",
    ]

    printed = set()
    for k in preferred_order:
        if k in counts:
            print(f"{k:16s} x{counts[k]}")
            printed.add(k)

    # Print any other unknown codes encountered
    for k in sorted(counts.keys()):
        if k not in printed:
            print(f"{k:16s} x{counts[k]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
