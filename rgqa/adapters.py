"""Sandbox-safe MesenCE driver. All frames are zero-based emulator frames.

There is deliberately no ROM-specific boot offset. Boot is part of the trace.
The endFrame callback samples RAM after frame F; inputPolled applies trace[F].
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

CAPABILITIES = {
    'input': True, 'memory': True, 'screenshots': False,
    'screenshot_reason': 'No proven frame-aligned headless framebuffer capture path',
}
BUTTONS = ('a', 'b', 'select', 'start', 'up', 'down', 'left', 'right')


class AdapterError(Exception):
    pass


@dataclass
class ReadProbe:
    name: str
    address: int
    width: int = 1
    frame: int = 0


@dataclass
class Comparison:
    probe: str
    op: str
    value: int | None = None


@dataclass
class ReplayReport:
    status: str
    frames_run: int = 0
    observations: list = field(default_factory=list)
    failing_frame: int | None = None
    message: str = ''
    raw_result: dict | None = None

    @property
    def ok(self):
        return self.status == 'pass'

    def summary(self):
        return f'{self.status.upper()} frame={self.failing_frame} observations={len(self.observations)} {self.message}'.strip()


def render_script(*, frame_table, probes, comparisons, max_frames):
    if max_frames < 1 or len(frame_table) != max_frames:
        raise AdapterError('trace length must equal max_frames')
    if len({p.name for p in probes}) != len(probes):
        raise AdapterError('duplicate checkpoint names')
    expressions = {'eq': '==', 'ne': '~=', 'lt': '<', 'le': '<=', 'gt': '>', 'ge': '>='}
    lines = [
        '-- Generated externally; no runtime filesystem or OS calls.',
        'local trace = {' + ','.join(map(str, frame_table)) + '}',
        'local frame = 0', 'local observations = {}', 'local failed = nil',
        'local done = false',
        'emu.addEventCallback(function()',
        '    local mask = trace[frame + 1] or 0',
        '    emu.setInput({' + ','.join(f'{b} = (mask & {1 << i}) ~= 0' for i, b in enumerate(BUTTONS)) + '}, 0)',
        'end, emu.eventType.inputPolled)',
        'emu.addEventCallback(function()', '    if done then return end',
    ]
    for p, c in zip(probes, comparisons, strict=True):
        read = f'emu.read({p.address}, emu.memType.nesMemory)'
        if p.width == 2:
            read += f' + 256 * emu.read({p.address + 1}, emu.memType.nesMemory)'
        if c.op in expressions:
            expr = f'v {expressions[c.op]} {c.value}'
        elif c.op in ('zero', 'nonzero'):
            expr = 'v == 0' if c.op == 'zero' else 'v ~= 0'
        else:
            raise AdapterError(f'unsupported comparison {c.op}')
        # Encode arbitrary human names as decimal escaped UTF-8 Lua literals.
        prefix = json.dumps({'name': p.name, 'frame': p.frame, 'address': p.address,
                             'span': p.width, 'op': c.op, 'expected': c.value},
                            ensure_ascii=True, separators=(',', ':'))[:-1]
        literal = '"' + ''.join(f'\\{b:03d}' for b in prefix.encode()) + '"'
        lines.extend([
            f'    if frame == {p.frame} then',
            f'        -- checkpoint {json.dumps(p.name)}: "frame":{p.frame}',
            f'        local v = {read}', f'        local ok = {expr}',
            f'''        local item = {literal} .. ',"value":' .. v .. ',"passed":' .. tostring(ok) .. '}}' ''',
            '        observations[#observations + 1] = item',
            '        if not ok and failed == nil then failed = frame end', '    end',
        ])
    lines.extend([
        f'    if frame == {max_frames - 1} then', '        done = true',
        '        local status = failed == nil and "pass" or "fail"',
        '''        print('RESULT:{"status":"' .. status .. '","frames_run":' .. (frame + 1) .. ',"failing_frame":' .. (failed or 'null') .. ',"observations":[' .. table.concat(observations, ',') .. ']}')''',
        '        emu.stop(0)', '    end', '    frame = frame + 1',
        'end, emu.eventType.endFrame)',
    ])
    return '\n'.join(lines) + '\n'


def parse_report(text, expected=None, max_frames=None):
    try:
        markers = [line[7:] for line in text.splitlines() if line.startswith('RESULT:')]
        if len(markers) != 1:
            raise ValueError('expected exactly one RESULT line')
        data = json.loads(markers[0])
        obs = data['observations']
        if not isinstance(obs, list) or not obs:
            raise ValueError('missing observations')
        if expected is not None and [(o['name'], o['frame']) for o in obs] != expected:
            raise ValueError('checkpoint observations incomplete or out of order')
        if any(type(o['value']) is not int or type(o['passed']) is not bool for o in obs):
            raise ValueError('invalid observation types')
        failing = min((o['frame'] for o in obs if not o['passed']), default=None)
        status = 'pass' if failing is None else 'fail'
        if data['status'] != status or data['failing_frame'] != failing:
            raise ValueError('inconsistent verdict')
        if max_frames is not None and data['frames_run'] != max_frames:
            raise ValueError('incomplete replay')
        return ReplayReport(status, data['frames_run'], obs, failing, raw_result=data)
    except (ValueError, KeyError, TypeError) as exc:
        return ReplayReport('error', message=f'invalid emulator protocol: {exc}')
