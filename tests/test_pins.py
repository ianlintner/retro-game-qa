import pytest
from conftest import base_manifest
from rgqa.manifest import load, ManifestError

@pytest.mark.parametrize('key', ['version','binary_sha256'])
def test_emulator_pins_required(key, write_manifest):
    doc = base_manifest()
    doc['emulator'].update(version='2.2.1',binary_sha256='0'*64)
    del doc['emulator'][key]
    with pytest.raises(ManifestError):
        load(write_manifest(doc))
