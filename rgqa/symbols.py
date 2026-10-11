"""ca65/ld65 label (.lbl) file loading.

`ld65 -Ln out.lbl` emits lines of the form::

    al 000300 .pad1_frame
    al 000302 .pad1_held

(the leading ``.`` comes from ca65's default anonymous/scoped label naming).
Mesen memory reads are addressed by raw 16-bit words, so all this module
really has to do is turn ``name -> address`` reliably, normalising the
decorated ca65 spelling so a manifest can say ``pad1_held`` without caring
how the assembler mangled it.
"""

from __future__ import annotations

import re
from pathlib import Path


class SymbolError(Exception):
    """Raised when a label file cannot be parsed or a symbol is missing."""


_LABEL_RE = re.compile(r"^(?P<kind>\w+)\s+(?P<addr>[0-9A-Fa-f]{4,8})\s+(?P<name>\S+)\s*$")


def _normalise(name: str) -> str:
    """Strip ca65's leading separator characters (``.``, ``__``)."""
    out = name
    while out.startswith(".") or out.startswith("__"):
        out = out[1:] if out.startswith(".") else out[2:]
    return out


def load_labels(path: str | Path) -> dict[str, int]:
    """Parse an ld65 label file into ``{normalised_name: address}``.

    Both the raw name and its normalised form are present as keys so callers
    can use either spelling; a collision keeps the last definition, which
    matches ld65's own overwrite semantics for ``.scope`` reuse.
    """
    p = Path(path)
    if not p.is_file():
        raise SymbolError(f"label file not found: {p}")

    labels: dict[str, int] = {}
    for lineno, raw in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        m = _LABEL_RE.match(line)
        if not m:
            # ld65 occasionally emits segment markers we do not care about.
            continue
        try:
            addr = int(m.group("addr"), 16)
        except ValueError as exc:  # pragma: no cover - regex already constrains
            raise SymbolError(f"{p}:{lineno}: bad address {m.group('addr')!r}") from exc
        # Only map RAM/register addresses; skip anything above the 16-bit space.
        if addr > 0xFFFF:
            continue
        name = m.group("name")
        labels[name] = addr
        labels.setdefault(_normalise(name), addr)
    return labels


class Symbols:
    """Address book for a single built ROM, with a strict lookup API."""

    def __init__(self, labels: dict[str, int], source: str | None = None) -> None:
        self._labels = dict(labels)
        self.source = source

    @classmethod
    def from_file(cls, path: str | Path) -> "Symbols":
        return cls(load_labels(path), source=str(path))

    def __contains__(self, name: str) -> bool:
        return name in self._labels

    def __len__(self) -> int:
        return len(self._labels)

    def address(self, name: str) -> int:
        """Resolve a symbol name to its 16-bit address.

        Raises ``SymbolError`` naming the symbol and the label file it came
        from, because "unknown symbol" with no source path is one of the most
        common time-sinks when a build silently used a stale .lbl.
        """
        try:
            return self._labels[name]
        except KeyError:
            where = f" (from {self.source})" if self.source else ""
            raise SymbolError(
                f"unknown symbol {name!r}{where}; available: "
                + ", ".join(sorted(self._labels)[:12])
            ) from None

    def get(self, name: str, default: int | None = None) -> int | None:
        return self._labels.get(name, default)
