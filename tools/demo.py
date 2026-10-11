"""Build reviewable demo manifests and record actual CLI results."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
out = root/'build/demo'
out.mkdir(parents=True, exist_ok=True)
rom = root/'fixtures/input-probe/build/input-probe.nes'
binary = Path(shutil.which(os.getenv('MESEN', 'Mesen')) or os.getenv('MESEN', 'Mesen'))
shutil.copy2(rom,out/'probe.nes')
shutil.copy2(root/'fixtures/input-probe/build/input-probe.lbl',out/'probe.lbl')
doc = {'schema_version':1,'id':'probe-input-smoke','description':'A held frames 8-11, released at 12',
 'target':{'rom':'probe.nes','sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'region':'ntsc'},
 'emulator':{'adapter':'mesence','min_version':'2.2.1','version':'2.2.1','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},
 'initial_state':'clean_boot','ports':[{'port':1,'device':'nes_controller'}],
 'trace':{'format':'frame_events_v1','frames':[{'frame':0,'held':[]},{'frame':8,'held':['a']},{'frame':12,'held':[]}]},
 'limits':{'max_frames':16,'timeout_seconds':10},
 'checkpoints':[{'name':'held','frame':10,'address':770,'space':'cpu_ram','span':1,'op':'eq','value':1},
 {'name':'released','frame':14,'address':770,'space':'cpu_ram','span':1,'op':'zero'},
 {'name':'count','frame':15,'symbol':'a_frames','symbols_from':'probe.lbl','segment_base':0,'span':1,'op':'eq','value':4}]}
transcript = []
for name, expected in [('pass',0),('fail',1),('stale',2),('corrupt',2)]:
    copy = json.loads(json.dumps(doc))
    if name == 'fail': copy['checkpoints'][0]['value'] = 99
    if name == 'stale': copy['target']['sha256'] = '0'*64
    src = out/(name+'.json')
    src.write_text('{broken' if name == 'corrupt' else json.dumps(copy,indent=2)+'\n')
    cmd = [sys.executable,'-m','rgqa',str(src),'--output',str(out/name),'--emulator',str(binary)]
    proc = subprocess.run(cmd,capture_output=True,text=True,cwd=root)
    text = f"command: {' '.join(cmd)}\nexit: {proc.returncode}\n{proc.stdout}{proc.stderr}"
    print(text)
    transcript.append(text)
    assert proc.returncode == expected
(out/'commands.txt').write_text('\n'.join(transcript))
