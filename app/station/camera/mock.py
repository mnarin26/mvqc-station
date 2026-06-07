"""Synthetic camera for development and CI (no hardware required).

Renders a deterministic scene with three component slots whose fill state can be
toggled, and modulates brightness from the current exposure/gain so teaching
sweeps and preview look realistic.
"""

from __future__ import annotations

import os
import time

import numpy as np

from .base import CameraBackend


class MockCamera(CameraBackend):
    name = "mock"

    # Slot rectangles (x, y, w, h) in the synthetic scene.
    _SLOTS = [(140, 180, 200, 200), (460, 180, 200, 200), (780, 180, 200, 200)]

    def __init__(self, settings) -> None:
        super().__init__(settings)
        # Which slots currently contain a component. Overridable via env for demos.
        env = os.environ.get("MVQC_MOCK_FILLED", "1,1,1")
        self._filled = [c.strip() == "1" for c in env.split(",")][:3]
        while len(self._filled) < 3:
            self._filled.append(True)

    def _open(self) -> None:
        pass

    def _close(self) -> None:
        pass

    def set_filled(self, filled: list[bool]) -> None:
        self._filled = list(filled)

    def _capture(self) -> np.ndarray:
        w = min(self.width, 1200)
        h = min(self.height, 600)
        # Neutral background with slight gradient + noise.
        frame = np.full((h, w, 3), 70, dtype=np.uint8)
        grad = np.linspace(0, 25, w, dtype=np.uint8)
        frame += grad[None, :, None]

        for idx, (x, y, sw, sh) in enumerate(self._SLOTS):
            if x + sw > w or y + sh > h:
                continue
            # Slot housing (dark border) + tray.
            frame[y:y + sh, x:x + sw] = (50, 50, 55)
            inner = 8
            xi, yi = x + inner, y + inner
            wi, hi = sw - 2 * inner, sh - 2 * inner
            if self._filled[idx]:
                # A "component": bright colored block with a highlight.
                color = [(120, 200, 245), (140, 225, 170), (235, 195, 130)][idx]
                frame[yi:yi + hi, xi:xi + wi] = color
                frame[yi:yi + hi // 3, xi:xi + wi] = [min(255, c + 20) for c in color]
            else:
                # Empty tray (uniform dark).
                frame[yi:yi + hi, xi:xi + wi] = (38, 38, 42)

        # Sensor noise.
        noise = np.random.normal(0, 4, frame.shape).astype(np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Exposure (EV-like) + gain brightness modulation.
        factor = float(np.clip((2.0 ** self._exposure) * max(self._gain, 0.1) / 1.0, 0.2, 4.0))
        if abs(factor - 1.0) > 1e-3:
            frame = np.clip(frame.astype(np.float32) * factor, 0, 255).astype(np.uint8)

        # Tiny temporal jitter so the live preview is visibly "live".
        shift = int((time.time() * 2) % 3)
        if shift:
            frame = np.roll(frame, shift, axis=1)
        return frame
