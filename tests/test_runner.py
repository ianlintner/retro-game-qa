import hashlib
import json
import subprocess
import sys
from pathlib import Path
from conftest import base_manifest
from rgqa.runner import Runner, RunnerConfig


def test_runner_rejects_stale_rom_before_launch(write_manifest):
    d = base_manifest()
    d['target']['rom'] = 'probe.nes'
    path = write_manifest(d)
    (path.parent / 'probe.nes').write_bytes(b'wrong')
    result = Runner().run_manifest(path)
    assert 'hash mismatch' in result.error


def test_cli_bad_json_emits_error_bundle(tmp_path):
    src = tmp_path / 'bad.json'
    src.write_text('{broken')
    out = tmp_path / 'evidence'
    proc = subprocess.run([sys.executable,'-m','rgqa',str(src),'--output',str(out)],capture_output=True,text=True)
    assert proc.returncode == 2
    report = json.loads((out/'result.json').read_text())
    assert report['status'] == 'error'
    assert report['capabilities']['screenshots'] is False


def test_protocol_missing_result_is_not_pass():
    from rgqa.adapters import parse_report
    assert parse_report('Loading rom').status == 'error'


def test_protocol_incomplete_replay_is_not_pass():
    from rgqa.adapters import parse_report
    text = 'RESULT:' + json.dumps({'status':'pass','frames_run':2,'failing_frame':None,
        'observations':[{'name':'a','frame':1,'value':0,'passed':True}]})
    assert parse_report(text, [('a',1),('b',2)], 3).status == 'error'
