"""AI-free playback entrypoint."""
import argparse
import json
from pathlib import Path
from .adapters import CAPABILITIES
from .runner import Runner, RunnerConfig


def main():
    parser = argparse.ArgumentParser(description='Deterministic NES replay (two clean runs)')
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--emulator', help='MesenCE executable; otherwise MESEN')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    result = Runner(RunnerConfig(emulator=args.emulator, script_dir=args.output)).run_manifest(args.manifest)
    status = 'error' if result.error or result.report is None else result.report.status
    evidence = {'schema_version':1, 'status':status, 'error':result.error,
                'manifest_id':result.manifest_id, 'capabilities':CAPABILITIES,
                'failing_frame':result.report.failing_frame if result.report else None,
                'observations':result.report.observations if result.report else []}
    evidence.update(getattr(result, 'evidence', {}))
    (args.output/'result.json').write_text(json.dumps(evidence, indent=2)+'\n')
    print(json.dumps({'status':status, 'failing_frame':evidence['failing_frame'],
                      'evidence':str((args.output/'result.json').resolve()), 'error':result.error}))
    return {'pass':0, 'fail':1, 'error':2}.get(status,2)


if __name__ == '__main__':
    raise SystemExit(main())
