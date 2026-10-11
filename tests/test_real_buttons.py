import os
import subprocess
from pathlib import Path
import pytest
from rgqa.adapters import ReadProbe, Comparison, render_script, parse_report

@pytest.mark.skipif(not os.getenv('RGQA_REAL'), reason='set RGQA_REAL=1 for real emulator')
@pytest.mark.parametrize('bit', range(8))
def test_fixture_serial_buttons_match_documented_ram(bit, tmp_path):
    root = Path(__file__).resolve().parents[1]
    lua = tmp_path / 'driver.lua'
    lua.write_text(render_script(frame_table=[0]*8+[1<<bit]*4+[0]*4,
        probes=[ReadProbe('held',770,frame=10)],
        comparisons=[Comparison('held','eq',1<<bit)],max_frames=16))
    log = tmp_path / 'stdout.log'
    subprocess.run(['bash',str(root/'tools/run-mesen.sh'),str(root/'fixtures/input-probe/build/input-probe.nes'),str(lua),str(log),'10'],check=False)
    report = parse_report(log.read_text())
    assert report.ok, report.raw_result
