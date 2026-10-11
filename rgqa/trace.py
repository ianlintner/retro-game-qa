"""Frame-indexed trace compilation to a concrete per-frame button table.

The manifest stores a *sparse* event list: each entry names the frame at which
a button set begins to be held, and that set stays held until a later entry
changes it. This module turns that into the *dense* per-frame table the
emulator driver actually consumes, and makes the idle/release semantics
explicit and testable rather than implied by the adapter.

Semantics (normative, mirrored in the schema description):

* Frame numbering is 0-based over emulator frames, including reset/boot.
  Frame 0 ends at the first endFrame callback; there is no game boot offset.
* Before the first event the controller is idle (no buttons held).
* An event's ``held`` set replaces the current held set entirely. A button
  omitted from a later event is therefore *released* at that frame. There is no
  implicit "sticky" behaviour.
* The table covers frames ``0 .. max_frame`` inclusive where ``max_frame`` is
  the highest frame any checkpoint samples, so every checkpoint always has an
  input value available.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Sequence, Tuple

#: Button name -> NES controller bit (MSB-first wire order as the fixture and
#: header comment document them). Kept here so the adapter never re-derives it.
BUTTON_BITS: Dict[str, int] = {
    "a": 0x01,
    "b": 0x02,
    "select": 0x04,
    "start": 0x08,
    "up": 0x10,
    "down": 0x20,
    "left": 0x40,
    "right": 0x80,
}


class TraceError(Exception):
    """The trace could not be compiled into a per-frame table."""


@dataclass(frozen=True)
class CompiledTrace:
    """A dense per-frame input table plus the frames that actually change.

    ``held`` maps every frame in ``[0, end_frame]`` to the button byte held
    during that frame. ``changes`` lists the frames at which that byte differs
    from the previous frame, which is what the Lua driver needs to emit.
    """

    held: Tuple[int, ...]
    end_frame: int

    def byte_at(self, frame: int) -> int:
        if frame < 0 or frame > self.end_frame:
            raise TraceError(
                "frame %d is outside the compiled trace range 0..%d"
                % (frame, self.end_frame)
            )
        return self.held[frame]

    def buttons_at(self, frame: int) -> FrozenSet[str]:
        byte = self.byte_at(frame)
        return frozenset(name for name, bit in BUTTON_BITS.items() if byte & bit)

    @property
    def changes(self) -> List[Tuple[int, int]]:
        """Frames whose held byte differs from the previous frame."""
        out: List[Tuple[int, int]] = []
        prev = 0  # implied idle before frame 0
        for frame, byte in enumerate(self.held):
            if byte != prev:
                out.append((frame, byte))
            prev = byte
        return out


def compile_trace(frames: Sequence, end_frame: int) -> CompiledTrace:
    """Expand sparse ``FrameEvent``s into a dense per-frame button table.

    ``frames`` is the manifest's ``trace.frames`` (objects with ``.frame`` and
    ``.held``); ``end_frame`` is the highest frame that must be representable
    (normally ``max(checkpoint.frame)``).
    """
    if end_frame < 0:
        raise TraceError("end_frame must be >= 0, got %d" % end_frame)

    events = sorted(frames, key=lambda e: e.frame)
    if not events:
        raise TraceError("trace has no frame events")
    if events[0].frame != 0:
        raise TraceError(
            "trace must start at frame 0; first event is frame %d" % events[0].frame
        )

    table: List[int] = []
    current = 0
    idx = 0
    # Walk every frame from 0 to end_frame, applying events as they arrive.
    for frame in range(0, end_frame + 1):
        while idx < len(events) and events[idx].frame == frame:
            current = _byte_for(events[idx].held, frame)
            idx += 1
        table.append(current)

    return CompiledTrace(held=tuple(table), end_frame=end_frame)


def _byte_for(held, frame: int) -> int:
    byte = 0
    for name in held:
        try:
            byte |= BUTTON_BITS[name]
        except KeyError:
            raise TraceError(
                "frame %d names unknown button %r; known: %s"
                % (frame, name, ", ".join(sorted(BUTTON_BITS)))
            )
    return byte
