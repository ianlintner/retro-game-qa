import pytest
from conftest import base_manifest
from rgqa.manifest import load, ManifestError


def test_byte_checkpoint_rejects_out_of_range_expected(write_manifest):
    doc = base_manifest()
    doc['checkpoints'][0]['span'] = 1
    doc['checkpoints'][0]['value'] = 256
    with pytest.raises(ManifestError, match='width'):
        load(write_manifest(doc))
