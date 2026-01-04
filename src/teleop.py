import threading
import time
from typing import Set

from lib.drone import Drone
from pynput import keyboard

NEUTRAL_VALUE = 127
SPEED_MULTIPLIER = 48
MOVEMENT_KEYS = ["w", "s", "a", "d", "i", "m"]


class TeleopSession:
    """Keyboard-driven teleoperation for the drone."""

    def __init__(self) -> None:
        self.drone = Drone()
        self._running = threading.Event()
        self._running.set()

        self._movement_pressed: Set[str] = set()
        self._movement_vector = [0, 0, 0]  # x, y, z

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

    def _update_movement_vector(self) -> None:
        self._movement_vector = [0, 0, 0]
        if "w" in self._movement_pressed:
            self._movement_vector[0] += 1
        if "s" in self._movement_pressed:
            self._movement_vector[0] -= 1
        if "a" in self._movement_pressed:
            self._movement_vector[1] -= 1
        if "d" in self._movement_pressed:
            self._movement_vector[1] += 1
        if "i" in self._movement_pressed:
            self._movement_vector[2] += 1
        if "m" in self._movement_pressed:
            self._movement_vector[2] -= 1

    def _apply_movement(self) -> None:
        pitch = NEUTRAL_VALUE + self._movement_vector[0] * SPEED_MULTIPLIER
        roll = NEUTRAL_VALUE + self._movement_vector[1] * SPEED_MULTIPLIER
        throttle = NEUTRAL_VALUE + self._movement_vector[2] * SPEED_MULTIPLIER

        self.drone.set_pitch(pitch)
        self.drone.set_roll(roll)
        self.drone.set_throttle(throttle)

    def on_press(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        key_char = getattr(key, "char", None)

        if key_char == "\x03":  # Ctrl+C
            self._running.clear()
            threading.interrupt_main()
            return False

        if key_char is None:
            # Special keys (e.g., arrows) are ignored
            return

        if key_char in MOVEMENT_KEYS:
            self._movement_pressed.add(key_char)
            self._update_movement_vector()
            self._apply_movement()

        if key_char == "q":
            self.drone.set_yaw(63)
        elif key_char == "e":
            self.drone.set_yaw(191)
        elif key_char == "r":
            self.drone.calibrate()
        elif key_char == "f":
            self.drone.takeoff()
        elif key_char == "v":
            self.drone.land()
        elif key_char == "c":
            self.drone.stop()
        elif key_char == "j":
            self.drone.reset_command()

    def on_release(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        if key == keyboard.Key.esc:
            self._running.clear()
            return False

        key_char = getattr(key, "char", None)
        if key_char is None:
            return None

        if key_char in MOVEMENT_KEYS and key_char in self._movement_pressed:
            self._movement_pressed.remove(key_char)
            self._update_movement_vector()
            self._apply_movement()

        return None

    def stop(self) -> None:
        self._running.clear()
        if self._drone_thread.is_alive():
            self._drone_thread.join()
        self.drone.stop()


if __name__ == "__main__":
    teleop = TeleopSession()
    try:
        while teleop._running.is_set():
            with keyboard.Listener(
                on_press=teleop.on_press,
                on_release=teleop.on_release,
            ) as listener:
                print("Ready To Teleop")
                listener.join()
    except KeyboardInterrupt:
        print("Interrupted!")
    finally:
        teleop.stop()
