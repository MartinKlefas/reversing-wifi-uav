import threading
import time
from typing import Literal

from lib.drone import Drone

NEUTRAL_VALUE = 127
MAX_SPEED = 123
Direction = Literal["forward", "back", "left", "right", "up", "down"]


class DroneTeleopAPI:
    """Simple API for commanding the drone without keyboard input."""

    def __init__(self):
        self.drone = Drone()
        self._running = threading.Event()
        self._running.set()
        self._initialize_drone()
        self._drone_thread = threading.Thread(target=self._background, daemon=True)
        self._drone_thread.start()

    def _initialize_drone(self) -> None:
        init_end = time.time() + 1
        while time.time() < init_end:
            self.drone.initialize_image()
            time.sleep(0.1)

    def _background(self) -> None:
        while self._running.is_set():
            self.drone.build_message()
            self.drone.send_message()
            time.sleep(0.1)

    def _clamp_speed(self, speed: int) -> int:
        return max(0, min(MAX_SPEED, speed))

    def _clamp_output(self, value: int) -> int:
        return max(0, min(255, value))

    def _reset_movement(self) -> None:
        self.drone.set_pitch(NEUTRAL_VALUE)
        self.drone.set_roll(NEUTRAL_VALUE)
        self.drone.set_throttle(NEUTRAL_VALUE)

    def move(self, direction: Direction, duration: float, speed: int) -> None:
        """Command a directional move for a specific duration.

        Args:
            direction: One of "forward", "back", "left", "right", "up", "down".
            duration: How long to hold the command in seconds.
            speed: Relative speed from 0 to 123 (mapped to byte offsets).
        """

        scaled_speed = self._clamp_speed(speed)
        pitch = NEUTRAL_VALUE
        roll = NEUTRAL_VALUE
        throttle = NEUTRAL_VALUE

        if direction == "forward":
            pitch += scaled_speed
        elif direction == "back":
            pitch -= scaled_speed
        elif direction == "right":
            roll += scaled_speed
        elif direction == "left":
            roll -= scaled_speed
        elif direction == "up":
            throttle += scaled_speed
        elif direction == "down":
            throttle -= scaled_speed
        else:
            raise ValueError(f"Unknown direction: {direction}")

        self.drone.set_pitch(self._clamp_output(pitch))
        self.drone.set_roll(self._clamp_output(roll))
        self.drone.set_throttle(self._clamp_output(throttle))

        time.sleep(max(0.0, duration))
        self._reset_movement()

    def shutdown(self) -> None:
        """Stop background messaging and reset the drone."""

        self._running.clear()
        if self._drone_thread.is_alive():
            self._drone_thread.join()
        self._reset_movement()
        self.drone.stop()


if __name__ == "__main__":
    api = DroneTeleopAPI()
    try:
        api.move("forward", duration=1.0, speed=48)
        api.move("up", duration=1.0, speed=48)
        api.move("back", duration=1.0, speed=48)
    finally:
        api.shutdown()
