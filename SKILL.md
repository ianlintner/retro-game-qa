---
name: retro-game-qa
description: "Use when authoring or replaying deterministic NES QA artifacts."
---

# Deterministic NES QA

Work from this repository root. Authoring may use AI; playback must never call a model.

1. Inspect `README.md`, `schemas/test-manifest.schema.json`, fixture RAM contract in `fixtures/input-probe/src/input_probe.s`, and existing manifests. Check git status; never modify another game repository to make a test pass.
2. Bootstrap Python with `python3 -m venv .venv` and `.venv/bin/python -m pip install -r requirements.txt`. Set `MESEN` to the executable for the tested MesenCE release, and `XVFB` to xvfb-run if it is not on PATH. See README for Linux dependencies.
3. Build before playback: `make -C fixtures/input-probe check`. Generated ROMs are not committed. Use only controlled or legally available ROMs.
4. Author a schema v1 manifest. Pin actual ROM SHA-256 and exact emulator binary SHA-256/version, NTSC, clean_boot, and NES controller port 1. Hash with `sha256sum "$MESEN" fixtures/input-probe/build/input-probe.nes`; do not copy old hashes after rebuilding. Paths resolve relative to the manifest. Use absolute ld65 labels with `segment_base: 0`. Checkpoint spans are one byte or little-endian two bytes in internal RAM only.
5. Input frames are zero-based emulator frames including boot. Before the first event input is idle; each held array replaces the whole previous state and persists until the next event. `held: []` releases all buttons. inputPolled applies frame F, endFrame observes F; never add a hidden ROM boot offset. Max frames is a count, so last valid frame is max_frames-1.
6. Execute `.venv/bin/python -m rgqa MANIFEST --output build/evidence/CASE --emulator "$MESEN"`. The runner performs two isolated portable clean boots and compares observations. The output directory is runner-owned; its run-N/engine folders are recreated. Exit 0=pass, 1=assertion failure, 2=invalid artifact, unsupported capability, identity mismatch, timeout, protocol failure or replay divergence.
7. Diagnose from result.json, both run-N/stdout.log files and generated driver.lua. An assertion failure includes its actual failing frame. Missing RESULT is infrastructure failure, not pass. Mesen exit alone is never evidence; bare print emits protocol, emu.log does not. Never insert io.*, os.*, dofile or takeScreenshot into headless Lua. No screenshot support is claimed.
8. Verify `.venv/bin/python -m pytest -q`, then `RGQA_REAL=1 .venv/bin/python -m pytest -q`, and `.venv/bin/python tools/demo.py`. The demo writes actual command/output receipts plus pass/fail/stale/corrupt bundles. Inspect input-held=1, released=0, a_frames=4, and negative failing frame=10 in both runs. Real tests also probe all eight buttons.
9. Review manifest, trace, resolved observations, identity pins, generated Lua and capabilities. Replay after every revision. Submit the source artifacts and evidence paths, not a screenshot substitute. Do not publish or merge without approval.

Future capture adapters must declare availability and produce real native framebuffer PNGs with checkpoint name, zero-based emulator frame, dimensions, pixel format, core identity, image hash and alignment proof. Unsupported requests must be rejected or explicitly unavailable, never synthetic. Keep visual baselines and tolerance approval separate from RAM assertions.
