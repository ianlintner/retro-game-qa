import os
from pathlib import Path
import pytest
from rgqa.symbols import Symbols

@pytest.mark.skipif(not os.getenv('RGQA_REAL'), reason='build fixture first')
def test_built_fixture_exports_ram_symbols():
    root = Path(__file__).resolve().parents[1]
    syms = Symbols.from_file(root/'fixtures/input-probe/build/input-probe.lbl')
    assert syms.address('a_frames') == 775
    assert syms.address('pad1_held') == 770
