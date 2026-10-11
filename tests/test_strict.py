import json
import pytest
from conftest import base_manifest
from rgqa.manifest import load, ManifestError


@pytest.mark.parametrize('mutation', [
    lambda d: d['checkpoints'][0].update(typo=True),
    lambda d: d['checkpoints'][0].update(op='changed', value=None),
    lambda d: d['ports'].append({'port': 2, 'device': 'nes_controller'}),
    lambda d: d['target'].update(region='pal'),
])
def test_unsupported_or_unknown_fields_rejected(write_manifest, mutation):
    d = base_manifest()
    mutation(d)
    with pytest.raises(ManifestError):
        load(write_manifest(d))


def test_missing_validator_fails_closed(write_manifest, monkeypatch):
    import rgqa.manifest as m
    monkeypatch.setattr(m, '_jsonschema', None)
    with pytest.raises(ManifestError, match='jsonschema'):
        load(write_manifest(base_manifest()))
