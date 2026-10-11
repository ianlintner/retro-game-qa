"""Manual real-emulator probe; prints actual RAM for each button."""
import os
import subprocess
from pathlib import Path
from rgqa.adapters import ReadProbe, Comparison, render_script

root = Path(__file__).resolve().parents[1]
out = root / 'build' / 'probe'
out.mkdir(parents=True, exist_ok=True)
for i, button in enumerate(('a','b','select','start','up','down','left','right')):
    script = render_script(frame_table=[0]*8 + [1 << i]*4 + [0]*4,
        probes=[ReadProbe('held', 770, frame=10), ReadProbe('a_count',775,frame=15), ReadProbe('right_count',774,frame=15)],
        comparisons=[Comparison('held','nonzero'),Comparison('a_count','ge',0),Comparison('right_count','ge',0)], max_frames=16)
    lua = out / (button + '.lua')
    lua.write_text(script)
    proc = subprocess.run(['bash',str(root/'tools/run-mesen.sh'), str(root/'fixtures/input-probe/build/input-probe.nes'),str(lua),str(out/(button+'.log')),'10'],capture_output=True,text=True)
    print(button, proc.returncode, (out/(button+'.log')).read_text(), proc.stderr)
