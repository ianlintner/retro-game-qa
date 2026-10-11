"""Manifest loading, schema validation, and cross-field checks.

Two layers, on purpose:

1. JSON Schema validation (``schemas/test-manifest.schema.json``) rejects
   anything structurally wrong, unsupported, or misspelled. Extra keys are
   forbidden at every level so a typo in a checkpoint field is a hard error
   rather than a silently ignored assertion.
2. Cross-field rules the schema cannot express: path containment, duplicate
   ports, trace monotonicity, bound consistency, and the "no inferred symbol
   addresses" rule.

A malformed manifest is always a :class:`ManifestError` with a message naming
the offending field, so an agent can fix it without reading the schema.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import dataclass, field
from typing import Any, Mapping

try:  # jsonschema is the real validator; the fallback keeps CI self-contained.
    import jsonschema as _jsonschema
except ImportError:  # pragma: no cover - exercised only without the dep
    _jsonschema = None

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schemas" / "test-manifest.schema.json"
SUPPORTED_SCHEMA_VERSIONS = (1,)

#: Operators that take no operand.
UNARY_OPS = frozenset({"nonzero", "zero", "changed", "unchanged"})
#: Operators that compare against ``value``.
BINARY_OPS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})


class ManifestError(Exception):
    """A manifest was missing, unparseable, or violated the contract."""


@dataclass(frozen=True)
class Target:
    rom: str
    sha256: str
    region: str


@dataclass(frozen=True)
class Emulator:
    adapter: str
    min_version: str
    version: str | None = None
    binary_sha256: str | None = None


@dataclass(frozen=True)
class Limits:
    max_frames: int
    timeout_seconds: int


@dataclass(frozen=True)
class Port:
    port: int
    device: str


@dataclass(frozen=True)
class FrameEvent:
    frame: int
    held: frozenset


@dataclass(frozen=True)
class Trace:
    format: str
    frames: tuple


@dataclass(frozen=True)
class Checkpoint:
    name: str
    frame: int
    op: str
    span: int
    kind: str  # "symbol" | "address"
    value: "int | None" = None
    symbol: "str | None" = None
    symbols_from: "str | None" = None
    segment_base: "int | None" = None
    address: "int | None" = None
    space: "str | None" = None


@dataclass(frozen=True)
class Manifest:
    id: str
    description: str
    target: Target
    emulator: Emulator
    initial_state: str
    ports: tuple
    trace: Trace
    limits: Limits
    checkpoints: tuple
    schema_version: int = 1
    path: "pathlib.Path | None" = None
    raw: Mapping = field(default_factory=dict, repr=False, compare=False)

    @property
    def root(self) -> pathlib.Path:
        """Directory the manifest's relative paths are resolved against."""
        return self.path.parent if self.path else pathlib.Path(".")


def _fail(msg: str) -> "ManifestError":
    return ManifestError(msg)


def _load_schema() -> dict:
    try:
        return json.loads(SCHEMA_PATH.read_text())
    except FileNotFoundError:  # pragma: no cover - ships with the repo
        raise ManifestError("manifest schema missing at %s" % SCHEMA_PATH)
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise ManifestError("manifest schema is not valid JSON: %s" % exc)


def _validate_structure(doc: Any, origin: str) -> None:
    if not isinstance(doc, dict):
        raise _fail("%s: manifest must be a JSON object" % origin)

    version = doc.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise _fail(
            "%s: unsupported schema_version %r (this runner implements %s)"
            % (origin, version, ", ".join(str(v) for v in SUPPORTED_SCHEMA_VERSIONS))
        )

    schema = _load_schema()
    if _jsonschema is not None:
        validator = _jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
        if errors:
            e = errors[0]
            where = "/".join(str(p) for p in e.absolute_path) or "<root>"
            raise _fail("%s: %s: %s" % (origin, where, e.message))
        return

    raise ManifestError('jsonschema is required; install requirements.txt')


def _validate_structure_fallback(doc: dict, origin: str) -> None:  # pragma: no cover
    """Minimal structural check used only when jsonschema is unavailable.

    Keeps the CI playback path dependency-free without silently accepting a
    malformed manifest. Unknown keys are rejected here too.
    """
    allowed = {
        "schema_version", "id", "description", "target", "emulator",
        "initial_state", "ports", "trace", "limits", "checkpoints",
        "screenshot_checkpoints",
    }
    extra = set(doc) - allowed
    if extra:
        raise _fail("%s: unknown top-level field(s): %s" % (origin, ", ".join(sorted(extra))))
    for key in ("id", "description", "target", "emulator", "initial_state",
                "ports", "trace", "limits", "checkpoints"):
        if key not in doc:
            raise _fail("%s: missing required field %r" % (origin, key))


# --- cross-field rules ------------------------------------------------------

def _check_paths(doc: dict, origin: str, root: "pathlib.Path | None" = None) -> None:
    rom = doc["target"]["rom"]
    if pathlib.PurePath(rom).is_absolute():
        raise _fail("%s: target/rom must be a relative path, got %r" % (origin, rom))
    if root is not None:
        resolved = (root / rom).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            raise _fail(
                "%s: target/rom %r escapes the manifest root; ROMs must live "
                "beside or below the manifest" % (origin, rom)
            )


def _check_ports(doc: dict, origin: str) -> None:
    if doc['target']['region'] != 'ntsc':
        raise _fail('Only ntsc is currently supported')
    seen = set()
    for p in doc["ports"]:
        n = p["port"]
        if n in seen:
            raise _fail("%s: duplicate port %d in ports[]" % (origin, n))
        seen.add(n)
    if seen != {1}:
        raise _fail('Only controller port 1 is supported')


def _check_trace(doc: dict, origin: str) -> None:
    frames = doc["trace"]["frames"]
    if frames[0]["frame"] != 0:
        raise _fail(
            "%s: trace/frames must start at frame 0 (first event is frame %d); "
            "state before any event is idle" % (origin, frames[0]["frame"])
        )
    prev = None
    for ev in frames:
        f = ev["frame"]
        if prev is not None and f <= prev:
            raise _fail(
                "%s: trace/frames must be strictly increasing; frame %d follows %d"
                % (origin, f, prev)
            )
        prev = f

    max_frames = doc["limits"]["max_frames"]
    if prev is not None and prev >= max_frames:
        raise _fail(
            "%s: trace references frame %d but limits/max_frames is %d"
            % (origin, prev, max_frames)
        )
    for cp in doc["checkpoints"]:
        if cp["frame"] >= max_frames:
            raise _fail(
                "%s: checkpoint %r samples frame %d but limits/max_frames is %d"
                % (origin, cp.get("name"), cp["frame"], max_frames)
            )


def _check_checkpoints(doc: dict, origin: str) -> None:
    names = set()
    for cp in doc["checkpoints"]:
        name = cp.get("name", "<unnamed>")
        if name in names:
            raise _fail('duplicate checkpoint name: %s' % name)
        names.add(name)
        extra = set(cp) - {'name', 'frame', 'op', 'value', 'span', 'symbol', 'symbols_from', 'segment_base', 'address', 'space'}
        if extra:
            raise _fail('unknown checkpoint fields: %s' % sorted(extra))
        if cp['op'] in ('changed', 'unchanged'):
            raise _fail('unsupported comparison: %s' % cp['op'])
        if cp.get('address', 0) + cp.get('span', 1) > 2048:
            raise _fail('cpu_ram observations must fit within NES internal RAM ($0000-$07ff)')
        op = cp["op"]
        has_symbol = "symbol" in cp
        has_address = "address" in cp

        if has_symbol and has_address:
            raise _fail(
                "%s: checkpoint %r has both symbol and address; pick one"
                % (origin, name)
            )
        if not has_symbol and not has_address:
            raise _fail(
                "%s: checkpoint %r needs either a symbol or an address" % (origin, name)
            )

        if has_symbol:
            if "symbols_from" not in cp:
                raise _fail(
                    "%s: checkpoint %r uses symbol but omits symbols_from; "
                    "symbol addresses are never inferred" % (origin, name)
                )
            if "segment_base" not in cp:
                raise _fail(
                    "%s: checkpoint %r uses symbol but omits segment_base; the "
                    "linker map stores offsets, so the base must be stated" % (origin, name)
                )

        if "span" not in cp:
            raise _fail(
                "%s: checkpoint %r must declare span (1 or 2)" % (origin, name)
            )

        if op in BINARY_OPS and "value" not in cp:
            raise _fail(
                "%s: checkpoint %r uses op %r and must supply value" % (origin, name, op)
            )
        if 'value' in cp and cp['value'] >= 256 ** cp['span']:
            raise _fail('checkpoint expected value exceeds observation width')
        if op in UNARY_OPS and "value" in cp:
            raise _fail(
                "%s: checkpoint %r uses unary op %r and must not supply value"
                % (origin, name, op)
            )

    if doc.get("screenshot_checkpoints"):
        raise _fail(
            "%s: screenshot_checkpoints are not supported by the mesence headless "
            "adapter (no proven capture path); remove them or use a visual-capable "
            "adapter" % origin
        )


# --- assembly ---------------------------------------------------------------

def load(path) -> Manifest:
    """Read and validate a manifest file, returning an immutable object."""
    p = pathlib.Path(path)
    try:
        text = p.read_text()
    except FileNotFoundError:
        raise _fail("manifest not found: %s" % p)
    except OSError as exc:
        raise _fail("cannot read manifest %s: %s" % (p, exc))

    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _fail("manifest %s is not valid JSON: %s" % (p, exc))

    origin = str(p)
    _validate_structure(doc, origin)
    _check_paths(doc, origin, root=p.parent)
    _check_ports(doc, origin)
    _check_trace(doc, origin)
    _check_checkpoints(doc, origin)

    return _assemble(doc, p)


def _assemble(doc: dict, path) -> Manifest:
    cps = []
    for cp in doc["checkpoints"]:
        cps.append(
            Checkpoint(
                name=cp["name"],
                frame=cp["frame"],
                op=cp["op"],
                span=cp["span"],
                kind="symbol" if "symbol" in cp else "address",
                value=cp.get("value"),
                symbol=cp.get("symbol"),
                symbols_from=cp.get("symbols_from"),
                segment_base=cp.get("segment_base"),
                address=cp.get("address"),
                space=cp.get("space"),
            )
        )
    return Manifest(
        id=doc["id"],
        description=doc["description"],
        target=Target(**doc["target"]),
        emulator=Emulator(**doc["emulator"]),
        initial_state=doc["initial_state"],
        ports=tuple(Port(**p) for p in doc["ports"]),
        trace=Trace(
            format=doc["trace"]["format"],
            frames=tuple(
                FrameEvent(frame=e["frame"], held=frozenset(e["held"]))
                for e in doc["trace"]["frames"]
            ),
        ),
        limits=Limits(**doc["limits"]),
        checkpoints=tuple(cps),
        schema_version=doc["schema_version"],
        path=path,
        raw=doc,
    )


def check_rom(manifest: Manifest) -> pathlib.Path:
    """Verify the ROM exists, is contained by the manifest root, and matches.

    A stale hash is a hard failure: replaying a trace against a different build
    is exactly the silent wrong-answer this project exists to prevent.
    """
    root = manifest.root.resolve()
    rom = (root / manifest.target.rom).resolve()
    try:
        rom.relative_to(root)
    except ValueError:
        raise _fail(
            "target/rom %r escapes the manifest root %s" % (manifest.target.rom, root)
        )
    if not rom.is_file():
        raise _fail("ROM not found: %s" % rom)

    digest = hashlib.sha256(rom.read_bytes()).hexdigest()
    if digest != manifest.target.sha256:
        raise _fail(
            "ROM hash mismatch for %s\n  manifest: %s\n  actual:   %s\n"
            "Refusing to replay a trace against a different build."
            % (rom, manifest.target.sha256, digest)
        )
    return rom
