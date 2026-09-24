"""What the practice duck's head camera sees: a room, rendered from where the mock stands.

The mock used to hand out one fixed 64x48 JPEG, which the Studio stretched into a blur and
which showed the person dead ahead whatever the duck did. This draws the mock's world instead —
a 12 m square room with a wooden floor and a floor grid that turns and slides as the duck
does, and the fake person at `person_xy` — through a pinhole camera 0.2 m above the floor.

Only the person's legs are dark (RGB sum well under 150); everything else stays light, so
`MockBarDetector` keeps finding exactly one blob. The focal length is the one that detector
assumes (`FX` scaled to the frame width), and the legs span `PERSON_WIDTH_M`, so the
bearing and the width-based range it reads off the picture are the true ones.

Deterministic and pure: the same pose gives the same bytes; the last frame is cached, so a duck
standing still costs one render.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence

from PIL import Image, ImageDraw

from ..perception.person_local import FX, PERSON_WIDTH_M, UPRIGHT_WIDTH

WIDTH, HEIGHT = 480, 360
FOCAL_PX = FX * WIDTH / UPRIGHT_WIDTH  # what MockBarDetector assumes for this width
CAMERA_HEIGHT_M = 0.20  # head camera of a standing 25 cm duck
CAMERA_HEIGHT_SITTING_M = 0.13
SUPERSAMPLE = 2  # draw at twice the size, then shrink: smooth edges without a real renderer
NEAR_M = 0.05

ROOM_HALF_M = 6.0
WALL_HEIGHT_M = 2.5
GRID_M = 0.5
BASEBOARD_M = 0.08

CEILING = (236, 237, 239)
FLOOR = (205, 184, 152)
GRID = (176, 152, 118)
SHADOW = (178, 160, 134)
BASEBOARD = (182, 184, 190)
# One tint per wall, so a turn is visible even with the floor grid out of sight.
WALLS = {
    "+x": (218, 226, 234),  # ahead at the start
    "+y": (232, 222, 208),
    "-x": (220, 230, 216),
    "-y": (230, 216, 222),
}
# The only dark things in the picture, and so what the detector finds: legs and shoes.
TROUSERS = (30, 36, 56)
SHOES = (22, 22, 26)
SHIRT = (214, 108, 84)
SKIN = (232, 190, 160)

Camera = tuple[float, float, float, float]  # x, y, heading, height
Point = tuple[float, float, float]  # world x, y, z


class MockCamera:
    def __init__(self, *, width: int = WIDTH, height: int = HEIGHT, quality: int = 85) -> None:
        self.width = width
        self.height = height
        self.quality = quality
        self._key: tuple[float, ...] | None = None
        self._jpeg = b""

    def render(
        self,
        *,
        x: float,
        y: float,
        heading: float,
        person_xy: tuple[float, float],
        sitting: bool = False,
    ) -> bytes:
        cam_h = CAMERA_HEIGHT_SITTING_M if sitting else CAMERA_HEIGHT_M
        key = (
            round(x, 3),
            round(y, 3),
            round(heading, 3),
            round(person_xy[0], 3),
            round(person_xy[1], 3),
            cam_h,
        )
        if key != self._key:
            self._jpeg = self._draw((x, y, heading, cam_h), person_xy)
            self._key = key
        return self._jpeg

    # -- drawing ------------------------------------------------------------------------

    def _draw(self, cam: Camera, person_xy: tuple[float, float]) -> bytes:
        s = SUPERSAMPLE
        img = Image.new("RGB", (self.width * s, self.height * s), CEILING)
        draw = ImageDraw.Draw(img)
        r = ROOM_HALF_M

        self._quad(draw, cam, [(-r, -r, 0.0), (r, -r, 0.0), (r, r, 0.0), (-r, r, 0.0)], FLOOR)
        steps = int(2 * r / GRID_M)
        for i in range(1, steps):
            g = -r + i * GRID_M
            self._segment(draw, cam, (g, -r, 0.0), (g, r, 0.0), GRID)
            self._segment(draw, cam, (-r, g, 0.0), (r, g, 0.0), GRID)

        # A convex room seen from inside: the walls never overlap, any order will do.
        corners = {
            "+x": ((r, -r), (r, r)),
            "+y": ((r, r), (-r, r)),
            "-x": ((-r, r), (-r, -r)),
            "-y": ((-r, -r), (r, -r)),
        }
        for name, ((ax, ay), (bx, by)) in corners.items():
            self._quad(
                draw,
                cam,
                [(ax, ay, 0.0), (bx, by, 0.0), (bx, by, WALL_HEIGHT_M), (ax, ay, WALL_HEIGHT_M)],
                WALLS[name],
            )
            self._quad(
                draw,
                cam,
                [(ax, ay, 0.0), (bx, by, 0.0), (bx, by, BASEBOARD_M), (ax, ay, BASEBOARD_M)],
                BASEBOARD,
            )

        self._person(draw, cam, person_xy)

        small = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        small.save(out, format="JPEG", quality=self.quality)
        return out.getvalue()

    def _person(
        self, draw: ImageDraw.ImageDraw, cam: Camera, person_xy: tuple[float, float]
    ) -> None:
        px, py = person_xy
        forward, _ = _to_camera(cam, px, py)
        if forward < 0.2:
            return
        half = PERSON_WIDTH_M / 2
        # Billboards facing the camera: a soft shadow, trousers with shoes, shirt, head.
        shadow = [
            _project(self, cam, (*_around(cam, px, py, dx, dy), 0.0))
            for dx, dy in _ellipse(0.22, 0.12)
        ]
        if all(p is not None for p in shadow):
            draw.polygon([p for p in shadow if p is not None], fill=SHADOW)
        leg = half * 0.42
        for side in (-1, 1):  # two legs, outer edges exactly PERSON_WIDTH_M apart
            self._billboard(draw, cam, px, py, leg, 0.0, 0.88, TROUSERS, left=side * (half - leg))
            self._billboard(draw, cam, px, py, leg, 0.0, 0.07, SHOES, left=side * (half - leg))
        self._billboard(draw, cam, px, py, half + 0.05, 0.86, 1.45, SHIRT)
        self._billboard(draw, cam, px, py, 0.05, 1.45, 1.52, SKIN)  # neck
        top = _project(self, cam, (px, py, 1.74))
        bottom = _project(self, cam, (px, py, 1.52))
        if top and bottom:
            radius = (bottom[1] - top[1]) / 2
            cx, cy = top[0], (top[1] + bottom[1]) / 2
            draw.ellipse(
                (cx - radius * 0.85, cy - radius, cx + radius * 0.85, cy + radius), fill=SKIN
            )

    def _billboard(
        self,
        draw: ImageDraw.ImageDraw,
        cam: Camera,
        px: float,
        py: float,
        half: float,
        z0: float,
        z1: float,
        colour: tuple[int, int, int],
        *,
        left: float = 0.0,
    ) -> None:
        # Offsets sideways in the camera frame, so the box always faces the duck.
        a = _around(cam, px, py, 0.0, left + half)
        b = _around(cam, px, py, 0.0, left - half)
        self._quad(
            draw,
            cam,
            [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)],
            colour,
        )

    def _quad(
        self,
        draw: ImageDraw.ImageDraw,
        cam: Camera,
        points: Sequence[Point],
        colour: tuple[int, int, int],
    ) -> None:
        clipped = _clip_near([_camera_space(cam, p) for p in points])
        if len(clipped) >= 3:
            draw.polygon([self._pixel(p) for p in clipped], fill=colour)

    def _segment(
        self,
        draw: ImageDraw.ImageDraw,
        cam: Camera,
        a: Point,
        b: Point,
        colour: tuple[int, int, int],
    ) -> None:
        ca, cb = _camera_space(cam, a), _camera_space(cam, b)
        if ca[0] < NEAR_M and cb[0] < NEAR_M:
            return
        if ca[0] < NEAR_M:
            ca = _lerp_to_near(cb, ca)
        elif cb[0] < NEAR_M:
            cb = _lerp_to_near(ca, cb)
        draw.line([self._pixel(ca), self._pixel(cb)], fill=colour, width=SUPERSAMPLE)

    def _pixel(self, p: Point) -> tuple[float, float]:
        """Camera-space (forward, left, up) to supersampled pixel coordinates."""
        s = SUPERSAMPLE
        forward, left, up = p
        u = self.width / 2 - FOCAL_PX * left / forward
        v = self.height / 2 - FOCAL_PX * up / forward
        return u * s, v * s


# -- geometry -------------------------------------------------------------------------------


def _to_camera(cam: Camera, wx: float, wy: float) -> tuple[float, float]:
    x, y, heading, _ = cam
    dx, dy = wx - x, wy - y
    c, s = math.cos(heading), math.sin(heading)
    return dx * c + dy * s, -dx * s + dy * c


def _camera_space(cam: Camera, p: Point) -> Point:
    forward, left = _to_camera(cam, p[0], p[1])
    return forward, left, p[2] - cam[3]


def _around(
    cam: Camera, px: float, py: float, d_forward: float, d_left: float
) -> tuple[float, float]:
    """A world point offset from (px, py) along the camera's forward and left axes."""
    heading = cam[2]
    c, s = math.cos(heading), math.sin(heading)
    return px + d_forward * c - d_left * s, py + d_forward * s + d_left * c


def _ellipse(a: float, b: float, n: int = 16) -> list[tuple[float, float]]:
    return [
        (a * math.cos(2 * math.pi * i / n), b * math.sin(2 * math.pi * i / n)) for i in range(n)
    ]


def _project(camera: MockCamera, cam: Camera, p: Point) -> tuple[float, float] | None:
    c = _camera_space(cam, p)
    return camera._pixel(c) if c[0] >= NEAR_M else None


def _lerp_to_near(inside: Point, outside: Point) -> Point:
    t = (inside[0] - NEAR_M) / (inside[0] - outside[0])
    return (
        NEAR_M,
        inside[1] + t * (outside[1] - inside[1]),
        inside[2] + t * (outside[2] - inside[2]),
    )


def _clip_near(points: list[Point]) -> list[Point]:
    """Sutherland–Hodgman against the plane forward = NEAR_M."""
    out: list[Point] = []
    for i, cur in enumerate(points):
        prev = points[i - 1]
        cur_in, prev_in = cur[0] >= NEAR_M, prev[0] >= NEAR_M
        if cur_in:
            if not prev_in:
                out.append(_lerp_to_near(cur, prev))
            out.append(cur)
        elif prev_in:
            out.append(_lerp_to_near(prev, cur))
    return out
