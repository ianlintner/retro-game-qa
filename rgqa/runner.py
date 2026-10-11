"""Replay runner: manifest -> compiled trace -> MesenCE -> report.

This is the orchestration layer. It owns no emulator knowledge itself; it
delegates Lua generation to :mod:`rgqa.adapters` and process handling to the
host wrapper script, so the emulator can be swapped without touching manifest
parsing or the CLI.

Manifest shape (see :mod:`rgqa.manifest`): a manifest is ONE replay with a flat
``checkpoints`` tuple, each checkpoint naming the frame it samples, the op, and
either a literal ``address`` or a ``symbol`` + ``symbols_from`` label file +
``segment_base`` (an explicit relocation addend; absolute ld65 labels use 0).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import CAPABILITIES, AdapterError, Comparison, ReadProbe, ReplayReport, parse_report, render_script
from .manifest import Checkpoint, Manifest, ManifestError, check_rom, load
from .symbols import SymbolError, Symbols
from .trace import compile_trace


class RunnerError(Exception):
    """Raised when a replay cannot be set up or executed."""


@dataclass
class SuiteResult:
    """Outcome of one manifest replay."""

    manifest_path: Path
    manifest_id: str = ""
    report: ReplayReport | None = None
    error: str = ""
    evidence: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error and self.report is not None and self.report.ok

    def summary(self) -> str:
        if self.error:
            return f"ERROR {self.manifest_id or self.manifest_path.name}: {self.error}"
        assert self.report is not None
        head = f"{self.manifest_id or self.manifest_path.name}: {self.report.summary()}"
        return head


@dataclass
class RunnerConfig:
    """Paths and knobs for a run, resolvable from env or explicitly."""

    emulator: str | None = None
    wrapper: Path | None = None
    timeout: int | None = None
    script_dir: Path | None = None


def _find_wrapper() -> Path:
    """Locate tools/run-mesen.sh relative to this package."""
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        cand = parent / "tools" / "run-mesen.sh"
        if cand.is_file():
            return cand
    raise RunnerError(
        "tools/run-mesen.sh not found; pass wrapper= explicitly or run from the repo"
    )


class Runner:
    """Executes one manifest's replay."""

    def __init__(self, config: RunnerConfig | None = None) -> None:
        self.config = config or RunnerConfig()

    def _wrapper(self) -> Path:
        if self.config.wrapper is not None:
            return self.config.wrapper
        return _find_wrapper()

    # -- address resolution --------------------------------------------

    def _symbols_cache(self, manifest: Manifest) -> dict[str, Symbols]:
        """Load every distinct label file the manifest references."""
        cache: dict[str, Symbols] = {}
        for cp in manifest.checkpoints:
            if cp.kind != "symbol" or not cp.symbols_from:
                continue
            if cp.symbols_from in cache:
                continue
            p = Path(cp.symbols_from)
            if not p.is_absolute():
                p = manifest.root / p
            try:
                cache[cp.symbols_from] = Symbols.from_file(p)
            except SymbolError as exc:
                raise RunnerError(f"checkpoint {cp.name!r}: {exc}") from exc
        return cache

    @staticmethod
    def resolve_address(cp: Checkpoint, labels: dict[str, Symbols]) -> int:
        """Resolve a checkpoint's byte address in NES memory space.

        A literal ``address`` is used verbatim. A ``symbol`` is looked up in its
        declared label file and offset by the explicit ``segment_base``.
        Absolute ld65 labels require base 0; relative maps need their RAM base.
        """
        if cp.kind == "address":
            if cp.address is None:
                raise RunnerError(f"checkpoint {cp.name!r} has no address")
            return cp.address
        if cp.symbol is None or cp.symbols_from is None:
            raise RunnerError(f"checkpoint {cp.name!r} has no symbol/symbols_from")
        syms = labels.get(cp.symbols_from)
        if syms is None:
            raise RunnerError(f"checkpoint {cp.name!r}: label file not loaded")
        base = cp.segment_base or 0
        return base + syms.address(cp.symbol)

    # -- script generation ---------------------------------------------

    def build_script(self, manifest: Manifest) -> str:
        """Compile the trace and render its sandbox-safe Lua script."""
        compiled = compile_trace(manifest.trace.frames, manifest.limits.max_frames - 1)

        labels = self._symbols_cache(manifest)

        probes: list[ReadProbe] = []
        comparisons: list[Comparison] = []
        for cp in sorted(manifest.checkpoints, key=lambda checkpoint: checkpoint.frame):
            addr = self.resolve_address(cp, labels)
            if not 0 <= addr <= 2048 - cp.span:
                raise RunnerError(f'checkpoint {cp.name}: resolved address outside internal RAM')
            probes.append(ReadProbe(name=cp.name, address=addr, width=cp.span, frame=cp.frame))
            comparisons.append(Comparison(probe=cp.name, op=cp.op, value=cp.value))

        try:
            return render_script(
                frame_table=list(compiled.held),
                probes=probes,
                comparisons=comparisons,
                max_frames=manifest.limits.max_frames,
            )
        except AdapterError as exc:
            raise RunnerError(f"manifest {manifest.id!r}: {exc}") from exc

    # -- execution -----------------------------------------------------

    def run_manifest(self, path: str | Path) -> SuiteResult:
        try:
            manifest = load(path)
            check_rom(manifest)
        except ManifestError as exc:
            result = SuiteResult(manifest_path=Path(path))
            result.error = str(exc)
            return result

        result = SuiteResult(manifest_path=Path(path), manifest_id=manifest.id)
        try:
            script = self.build_script(manifest)
        except (RunnerError, SymbolError) as exc:
            result.error = str(exc)
            return result

        scratch = self.config.script_dir or Path(
            tempfile.mkdtemp(prefix="rgqa-")
        )
        scratch.mkdir(parents=True, exist_ok=True)
        lua_path = scratch / f"{manifest.id}.lua"
        log_path = scratch / f"{manifest.id}.log"
        lua_path.write_text(script)

        try:
            command = self.config.emulator or os.getenv('MESEN', 'Mesen')
            binary = Path(shutil.which(command) or command).resolve()
            data = binary.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            versions = re.findall(rb'([0-9]+\.[0-9]+\.[0-9]+)\+([0-9a-f]{40})', data)
            matches = {v.decode() for v, commit in versions if v.decode() == manifest.emulator.version}
            if not manifest.emulator.version or not manifest.emulator.binary_sha256:
                raise RunnerError('execution requires emulator.version and emulator.binary_sha256 pins')
            if digest != manifest.emulator.binary_sha256:
                raise RunnerError('emulator binary hash mismatch')
            if manifest.emulator.version not in matches:
                raise RunnerError('pinned emulator version not found in embedded build metadata')
            if tuple(map(int, manifest.emulator.version.split('.'))) < tuple(map(int, manifest.emulator.min_version.split('.'))):
                raise RunnerError('emulator version is below min_version')
        except (OSError, RunnerError) as exc:
            result.error = str(exc)
            return result
        result.evidence = {'rom_sha256':manifest.target.sha256, 'emulator':{'version':manifest.emulator.version,
            'binary_sha256':digest, 'version_source':'embedded assembly build metadata'},
            'manifest_sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            'trace_sha256':hashlib.sha256(json.dumps([{'frame':e.frame,'held':sorted(e.held)} for e in manifest.trace.frames],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'capabilities': CAPABILITIES.copy(),
            'deterministic':False, 'runs':[]}
        source_doc = json.loads(Path(path).read_text())
        (scratch/'manifest.json').write_text(json.dumps(source_doc,indent=2)+'\n')
        reports = []
        for number in (1,2):
            run_dir = scratch / f'run-{number}'
            run_dir.mkdir(parents=True,exist_ok=True)
            driver = run_dir/'driver.lua'
            driver.write_text(script)
            report = self._execute(manifest, driver, run_dir/'stdout.log', binary)
            reports.append(report)
            result.evidence['runs'].append({'status':report.status,'frames_run':report.frames_run,
                'failing_frame':report.failing_frame,'observations':report.observations,'message':report.message})
        result.report = reports[0]
        same = result.evidence['runs'][0] == result.evidence['runs'][1]
        result.evidence['deterministic'] = same and all(r.status in ('pass','fail') for r in reports)
        if not result.evidence['deterministic']:
            result.error = 'clean replay divergence or emulator error'
        return result

    def _execute(self, manifest: Manifest, lua: Path, log: Path, binary: Path) -> ReplayReport:
        wrapper = self._wrapper()
        timeout = self.config.timeout or manifest.limits.timeout_seconds
        rom = (manifest.root / manifest.target.rom).resolve()
        cmd = [
            "bash",
            str(wrapper),
            str(rom),
            str(lua),
            str(log),
            str(timeout),
        ]
        env = dict(os.environ)
        engine = lua.parent/'engine'
        if engine.exists():
            shutil.rmtree(engine)
        engine.mkdir()
        shutil.copy2(binary, engine/'Mesen')
        settings = {'Nes':{'Region':'Ntsc','RamPowerOnState':'AllZeros',
            'Port1':{'Type':'NesController'}, 'Port2':{'Type':'None'}},
            'Emulation':{'EnableRandomPowerOnState':False}}
        (engine/'settings.json').write_text(json.dumps(settings,indent=2)+'\n')
        env['MESEN'] = str((engine/'Mesen').resolve())
        env['RGQA_PORTABLE'] = '1'
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 30,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return ReplayReport(status="error", message="host wrapper timed out")

        text = ""
        if log.is_file():
            text = log.read_text(encoding="utf-8", errors="replace")
        if not text:
            text = (proc.stdout or "") + (proc.stderr or "")
        if not text:
            return ReplayReport(
                status="error",
                message=f"no emulator output (wrapper exit {proc.returncode})",
            )
        if proc.returncode not in (0,1):
            return ReplayReport('error', message=f'wrapper failed or timed out: {proc.returncode}')
        expected = [(c.name,c.frame) for c in manifest.checkpoints]
        expected.sort(key=lambda item:item[1])
        return parse_report(text, expected, manifest.limits.max_frames)
