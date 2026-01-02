import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

import tkinter as tk

from lib.drone import Drone


Point = Tuple[int, int]


@dataclass
class RCCommand:
    pitch: int = 127
    roll: int = 127
    throttle: int = 127


class PathCommandSender:
    """
    Convert a list of 2D points into RC commands and send them to the drone.

    The drone is assumed to face "north" for the full path, so movement is
    derived directly from the x/y deltas (no yaw commands). Positive roll moves
    east, positive pitch moves south, and throttle stays constant unless
    overridden.
    """

    def __init__(
        self,
        drone: Optional[Drone] = None,
        send_callback: Optional[Callable[[RCCommand], None]] = None,
        step_delay: float = 0.25,
        speed_multiplier: int = 48,
        pixel_scale: float = 50.0,
    ) -> None:
        self.drone = drone if send_callback is None else None
        self.send_callback = send_callback
        self.step_delay = step_delay
        self.speed_multiplier = speed_multiplier
        self.pixel_scale = pixel_scale

        self._running = False
        self._drone_thread: Optional[threading.Thread] = None

        if self.drone:
            self._start_background_sender()

    def _start_background_sender(self) -> None:
        self._running = True
        self._drone_thread = threading.Thread(target=self._drone_loop, daemon=True)
        self._drone_thread.start()

    def _drone_loop(self) -> None:
        assert self.drone is not None
        while self._running:
            self.drone.build_message()
            self.drone.send_message()
            time.sleep(0.1)

    def stop(self) -> None:
        self._running = False
        if self._drone_thread:
            self._drone_thread.join(timeout=1)

    def _clamp(self, value: int, minimum: int = 0, maximum: int = 255) -> int:
        return max(minimum, min(maximum, value))

    def _delta_to_command(self, dx: float, dy: float, base: RCCommand) -> RCCommand:
        roll_offset = (dx / self.pixel_scale) * self.speed_multiplier
        # y on the canvas grows downward, so moving north (negative dy) means
        # increasing pitch.
        pitch_offset = (-dy / self.pixel_scale) * self.speed_multiplier

        pitch = self._clamp(int(base.pitch + pitch_offset))
        roll = self._clamp(int(base.roll + roll_offset))

        return RCCommand(pitch=pitch, roll=roll, throttle=base.throttle)

    def _send(self, command: RCCommand) -> None:
        if self.drone:
            self.drone.set_pitch(command.pitch)
            self.drone.set_roll(command.roll)
            self.drone.set_throttle(command.throttle)
        if self.send_callback:
            self.send_callback(command)

    def follow_path(self, points: Iterable[Point], base: Optional[RCCommand] = None) -> List[RCCommand]:
        base_command = base or RCCommand()
        commands: List[RCCommand] = []

        point_list = list(points)
        if len(point_list) < 2:
            return commands

        for start, end in zip(point_list, point_list[1:]):
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            command = self._delta_to_command(dx, dy, base_command)
            commands.append(command)
            self._send(command)
            time.sleep(self.step_delay)

        # Return to hover
        self._send(base_command)
        commands.append(base_command)
        return commands


class SimpleDraw(tk.Tk):
    def __init__(self, sender: Optional[PathCommandSender] = None):
        super().__init__()
        self.title("Draw a path (LMB drag). Press Export.")
        self.geometry("800x600")

        self.canvas = tk.Canvas(self, bg="white")
        self.canvas.pack(fill="both", expand=True)

        btn = tk.Button(self, text="Export points", command=self.export)
        btn.pack()

        self.points: List[Point] = []
        self._last: Optional[Point] = None
        self.sender = sender

        self.canvas.bind("<ButtonPress-1>", self.on_down)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_up)

    def on_down(self, event):
        self._last = (event.x, event.y)
        self.points.append(self._last)

    def on_drag(self, event):
        cur = (event.x, event.y)
        if self._last:
            self.canvas.create_line(self._last[0], self._last[1], cur[0], cur[1], width=3)
        self._last = cur
        self.points.append(cur)

    def on_up(self, event):
        self._last = None

    def export(self):
        print(f"Exported {len(self.points)} points")
        print(self.points[:10], "...")
        if self.sender:
            print("Sending path to drone...")
            self.sender.follow_path(self.points)
            print("Done sending path. Drone should remain facing north for this flight.")


if __name__ == "__main__":
    sender = PathCommandSender()
    try:
        SimpleDraw(sender=sender).mainloop()
    finally:
        sender.stop()
