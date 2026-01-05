import math
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

import pygame

from lib.drone import Drone


Point = Tuple[int, int]
CANVAS_BG = (255, 255, 255)
PATH_COLOR = (20, 90, 200)
ERASE_PREVIEW = (230, 80, 80)
INFO_BG = (40, 40, 40)
INFO_TEXT = (230, 230, 230)


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


class SimpleDraw:
    def __init__(self, sender: Optional[PathCommandSender] = None, size: Tuple[int, int] = (960, 720)):
        pygame.init()
        self.screen = pygame.display.set_mode(size)
        pygame.display.set_caption(
            "Draw path with LMB. Space: send path. E: toggle eraser. C: clear."
        )
        self.canvas = pygame.Surface(size)
        self.canvas.fill(CANVAS_BG)
        self.font = pygame.font.Font(None, 24)

        self.points: List[Point] = []
        self._last: Optional[Point] = None
        self._drawing = False
        self._running = True
        self.eraser_enabled = False
        self.eraser_radius = 14
        self.sender = sender

        self.size = size

    def _render_text(self) -> None:
        info_lines = [
            "LMB drag to draw path",
            "Space: send/fly | C: clear | E: toggle eraser | Esc/Close: quit",
            f"Eraser: {'ON' if self.eraser_enabled else 'OFF'} (radius {self.eraser_radius}px)",
            f"Points: {len(self.points)}",
        ]
        info_height = 70
        info_rect = pygame.Rect(0, 0, self.size[0], info_height)
        pygame.draw.rect(self.screen, INFO_BG, info_rect)

        y = 8
        for line in info_lines:
            text_surf = self.font.render(line, True, INFO_TEXT)
            self.screen.blit(text_surf, (10, y))
            y += 18

    def _redraw_canvas(self) -> None:
        self.canvas.fill(CANVAS_BG)
        if len(self.points) < 2:
            return

        last = self.points[0]
        for point in self.points[1:]:
            pygame.draw.line(self.canvas, PATH_COLOR, last, point, 3)
            last = point

    def _add_point(self, pos: Point) -> None:
        if self._last is not None:
            pygame.draw.line(self.canvas, PATH_COLOR, self._last, pos, 3)
        self.points.append(pos)
        self._last = pos

    def _erase_at(self, pos: Point) -> None:
        px, py = pos
        before = len(self.points)
        self.points = [p for p in self.points if math.hypot(p[0] - px, p[1] - py) > self.eraser_radius]
        if len(self.points) != before:
            self._last = None
            self._redraw_canvas()

    def _clear(self) -> None:
        self.points.clear()
        self._last = None
        self.canvas.fill(CANVAS_BG)

    def _export(self) -> None:
        if not self.points:
            print("No points to export.")
            return
        print(f"Exported {len(self.points)} points")
        print(self.points[:10], "...")
        if self.sender:
            print("Sending path to drone...")
            self.sender.follow_path(self.points)
            print("Done sending path. Drone should remain facing north for this flight.")

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            self._drawing = True
            self._add_point(event.pos)

    def _handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button == 1:
            self._drawing = False
            self._last = None

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if not self._drawing:
            return
        if self.eraser_enabled:
            self._erase_at(event.pos)
        else:
            self._add_point(event.pos)

    def _draw_eraser_preview(self, mouse_pos: Point) -> None:
        if not self.eraser_enabled:
            return
        pygame.draw.circle(self.screen, ERASE_PREVIEW, mouse_pos, self.eraser_radius, 2)

    def run(self) -> None:
        clock = pygame.time.Clock()
        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._running = False
                    elif event.key == pygame.K_SPACE:
                        self._export()
                    elif event.key == pygame.K_c:
                        self._clear()
                    elif event.key == pygame.K_e:
                        self.eraser_enabled = not self.eraser_enabled
                        self._last = None
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_mouse_down(event)
                elif event.type == pygame.MOUSEBUTTONUP:
                    self._handle_mouse_up(event)
                elif event.type == pygame.MOUSEMOTION:
                    self._handle_mouse_motion(event)

            self.screen.blit(self.canvas, (0, 0))
            self._render_text()
            self._draw_eraser_preview(pygame.mouse.get_pos())
            pygame.display.flip()
            clock.tick(120)

        pygame.quit()


if __name__ == "__main__":
    sender = PathCommandSender()
    try:
        SimpleDraw(sender=sender).run()
    finally:
        sender.stop()
