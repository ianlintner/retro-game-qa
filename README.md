# Retro Game QA

A local-first, deterministic tool-assisted test runner for retro games. This repository is a work in progress. The objective is to let coding agents author test artifacts while CI replays them without any model calls.

## Contract for the first implementation

- A test consists of a human-reviewable manifest plus a frame-indexed controller trace. Define the schema in this repo, validate malformed and unsupported fields, and keep playback independent of AI.
- Pin emulator/core identity and version, ROM SHA-256, console region, initial state (clean boot by default), controller ports and trace format. A ROM mismatch must fail clearly rather than replaying against the wrong build.
- Inputs are unambiguous by frame (including release/idle); a test has a maximum emulated-frame count and a wall-clock timeout. Two isolated runs of the same test should produce the same checkpoint state and trace result.
- Checkpoints assert named game-state symbols or explicit memory addresses. Symbols are build-specific and must be resolved from build artifacts; do not infer their addresses silently. Keep visual checkpoints and approved screenshot baselines distinct from gameplay assertions.
- Output an evidence bundle with result JSON, ROM hash, emulator version, failing frame, checkpoint observations, and the replayable trace. Screenshots must be real emulator output when supported and must be reported as unavailable otherwise; never use synthetic screenshots as evidence.
- Adapters declare their capabilities. The first adapter is MesenCE 2.2.1 or later for NES headless input, memory assertions, and exit status. Its `--testRunner` Lua sandbox denies file and screenshot I/O: preprocess/inject scripts from outside Lua and do not claim `emu.takeScreenshot()` works there. Implement a separate proven video capture path before calling screenshots supported.
- Provide a project-local agent skill describing inspect → build → author/record → run → diagnose → revise → run again from clean state → submit artifact. Agent generation is authoring only; the replay path must be deterministic and AI-free.
- Initial integration target: an existing NES project or a tiny controlled ROM fixture, with at least one positive route and one intentionally failing assertion whose failure frame is shown. Follow with a screenshot-capture spike and an additional console adapter (for example libretro) only once the NES contract is proven.

## Scope boundaries

Do not mutate an existing game repository to make a demo pass. Keep artifacts small and reviewable, and avoid embedding copyrighted ROMs. This public baseline contains only the reviewed NES runner; visual-capture and Game Boy portability branches remain local until separately reviewed. Released under the MIT license (see `LICENSE`). Add CI only for tests that can run in the target environment. Pin dependencies and document bootstrap requirements.

## Running the implemented NES adapter

Linux prerequisites: Python 3.11+, cc65 (ca65/ld65), Xvfb, xauth, timeout
(coreutils), and the native runtime libraries required by MesenCE. On
Debian/Ubuntu: `sudo apt-get install cc65 xvfb xauth libgtk-3-0 libsdl2-2.0-0`;
on Arch install `cc65 xorg-server-xvfb xorg-xauth gtk3 sdl2`. These are setup
instructions, not commands run by playback.

Download the Linux x64 asset `Mesen_2.2.1_Linux_x64.zip` from
https://github.com/nesdev-org/MesenCE/releases/tag/2.2.1, extract it to a
user-owned directory, `chmod +x Mesen`, and export `MESEN=/absolute/path/Mesen`.
Export `XVFB=/absolute/path/xvfb-run` if it is not on PATH. Version 2.2.1 is
verified here; later releases require requalification of callback semantics
and embedded version metadata before updating exact pins. Do not use the
archived SourMesen 2.1.1 NativeAOT binary, which crashes in headless mode here.

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
make -C fixtures/input-probe check
.venv/bin/python -m pytest -q
RGQA_REAL=1 .venv/bin/python -m pytest -q
.venv/bin/python tools/demo.py
.venv/bin/python -m rgqa build/demo/pass.json --output build/replay --emulator "$MESEN"
```

`tools/demo.py` computes actual pins and generates pass/fail/stale/corrupt
manifests, runs the CLI and saves actual commands/output in
`build/demo/commands.txt`. `examples/probe-input-smoke.json` is a pinned example
for the tested binary and fixture; copy it beside the built ROM/labels or run
the demo generator, and regenerate pins for a different build. ROM paths must
stay beside or below the manifest root (no parent traversal).
The controlled ROM has no copyrighted game data and is rebuilt from source.

### Supported v1 semantics

Frames are zero-based emulator frames, including boot; max_frames is a count.
inputPolled applies trace[F], and endFrame samples checkpoint F. Input is idle
before the first event. Each held set replaces all buttons and persists until
the next event; an empty array releases everything. There is no ROM-specific
boot offset. NTSC, clean_boot and controller port 1 are the only supported
configuration. The runner starts each replay with fresh portable settings,
zeroed RAM and disabled random power-on state, ignoring user emulator settings
and removing stale files in its owned run-N/engine folder.

Required identities are ROM SHA-256 and emulator version plus binary SHA-256.
The Linux native executable version is checked against embedded build metadata;
a filename is not version evidence. Manifests are Draft 2020-12 JSON Schema
validated and then checked for trace ordering, unique checkpoints, RAM bounds,
value width, unsupported fields and capabilities. jsonschema is mandatory.

Checkpoints support eq/ne/lt/le/gt/ge/zero/nonzero, one-byte or two-byte
little-endian observations in $0000-$07ff. Literal addresses are explicit.
Symbol maps resolve against declared build artifacts; ld65 -Ln labels are
absolute, so use segment_base=0 (nonzero is only for genuinely relative maps).
ROM paths and symbol paths are relative to the manifest, not the current cwd.

CLI exits: 0 pass, 1 assertion failure, 2 setup/validation/protocol/timeout or
replay divergence. Both passes and deliberate failures must agree across two
clean boots. Mesen's process exit is not the verdict: complete RESULT protocol,
checkpoint frames and observation types are validated on the host.

### Evidence and future capture

The output directory contains result.json (verdict, failing frame, identities,
manifest/trace hashes, capabilities and both run observations), manifest.json
(the original reviewable trace), generated Lua, and run-1/run-2/driver.lua,
stdout.log and engine/settings.json. stdout and stderr from the emulator are
captured together on the host. Engine binary copies are runtime-only, not
source or deliverables; each run needs disk space for one executable copy.
Output directories are runner-owned; do not put personal files in run-N/engine.

Screenshots are unavailable, with a reason in capabilities. Headless Lua uses
no OS/filesystem calls. A future adapter must declare screenshot availability,
return native unfiltered framebuffer PNGs keyed by checkpoint/frame, record
resolution, pixel format, core/version/hash and image SHA-256, and demonstrate
frame alignment. Never promote desktop captures or generated images as proof.
Visual-baseline approvals and tolerances remain separate from RAM assertions.
The project-local agent workflow is in `SKILL.md`.

## References

- [Mesen Lua API and headless test runner](https://www.mesen.ca/docs/apireference.html)
- [libretro core loop and callbacks](https://docs.libretro.com/development/cores/developing-cores)
