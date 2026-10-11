import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

@pytest.mark.skipif(not os.getenv('RGQA_REAL'), reason='set RGQA_REAL=1')
def test_cli_two_clean_replays_and_negative(tmp_path):
    root = Path(__file__).resolve().parents[1]
    binary = Path(os.getenv('MESEN', 'Mesen'))
    rom = root/'fixtures/input-probe/build/input-probe.nes'
    import shutil
    shutil.copy2(rom, tmp_path/'probe.nes')
    shutil.copy2(root/'fixtures/input-probe/build/input-probe.lbl', tmp_path/'probe.lbl')
    doc = {'schema_version':1,'id':'real','description':'real A hold/release',
      'target':{'rom':'probe.nes','sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'region':'ntsc'},
      'emulator':{'adapter':'mesence','min_version':'2.2.1','version':'2.2.1','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},
      'initial_state':'clean_boot','ports':[{'port':1,'device':'nes_controller'}],
      'trace':{'format':'frame_events_v1','frames':[{'frame':0,'held':[]},{'frame':8,'held':['a']},{'frame':12,'held':[]}]},
      'limits':{'max_frames':16,'timeout_seconds':10},
      'checkpoints':[{'name':'held','frame':10,'address':770,'space':'cpu_ram','span':1,'op':'eq','value':1},
                     {'name':'released','frame':14,'address':770,'space':'cpu_ram','span':1,'op':'zero'},
                     {'name':'count','frame':15,'symbol':'a_frames','symbols_from':'probe.lbl','segment_base':0,'span':1,'op':'eq','value':4}]}
    src = tmp_path/'test.json'
    for status, expected_exit in [('pass',0),('fail',1)]:
        if status == 'fail': doc['checkpoints'][0]['value'] = 99
        src.write_text(json.dumps(doc))
        out = tmp_path/status
        stale = out/'run-1/engine/SaveStates/stale.mst'
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_bytes(b'stale state')
        proc = subprocess.run([sys.executable,'-m','rgqa',str(src),'--output',str(out),'--emulator',str(binary)],capture_output=True,text=True)
        assert proc.returncode == expected_exit, (proc.stdout,proc.stderr)
        result = json.loads((out/'result.json').read_text())
        assert result['deterministic'] is True
        assert len(result['runs']) == 2
        assert result['runs'][0]['observations'] == result['runs'][1]['observations']
        assert result['failing_frame'] == (10 if status=='fail' else None)
        assert not stale.exists()
        assert (out/'run-1/engine/settings.json').exists()
        assert (out/'run-2/engine/settings.json').exists()
