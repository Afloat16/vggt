import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


parser = argparse.ArgumentParser()
parser.add_argument('--test', required=True)
parser.add_argument('--base', required=True)
parser.add_argument('--sources', required=True)
parser.add_argument('--count', type=int, required=True)
args = parser.parse_args()
sources = json.loads(args.sources)
test = Path(args.test)
candidate_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
report = {'candidate': candidate_sha, 'baseline': args.base, 'test': args.test, 'python': sys.version, 'results': {}}


def run(mode):
    loader = unittest.TestLoader()
    suite = loader.discover(str(test.parent), pattern=test.name)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    import_failures = [t.id() for t, _ in result.errors if t.__class__.__name__ == '_FailedTest']
    report['results'][mode] = {
        'tests': result.testsRun,
        'failures': [t.id() for t, _ in result.failures],
        'errors': [t.id() for t, _ in result.errors],
        'imports_failed': import_failures,
        'skipped': [t.id() for t, _ in result.skipped],
        'sources': {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources},
    }
    if import_failures or result.skipped or result.testsRun != args.count:
        raise RuntimeError(f'{mode}: failed to load the complete native test suite')
    if mode == 'candidate' and not result.wasSuccessful():
        raise RuntimeError('Candidate regression tests failed')
    if mode == 'baseline' and result.wasSuccessful():
        raise RuntimeError('The regression suite does not distinguish the baseline')


try:
    run('candidate')
    for path in sources:
        original = subprocess.check_output(['git', 'show', f'{args.base}:{path}'])
        Path(path).write_bytes(original)
    # Use a separate process so imported candidate modules and bytecode cannot
    # be reused while checking the original production files.
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    for directory in Path('.').rglob('__pycache__'):
        for bytecode in directory.glob('*.pyc'):
            bytecode.unlink()
    code = (
        'import unittest,json,pathlib; '
        f's=unittest.TestLoader().discover({str(test.parent)!r},pattern={test.name!r}); '
        'r=unittest.TextTestRunner(verbosity=2).run(s); '
        'd={"tests":r.testsRun,"failures":[t.id() for t,_ in r.failures],'
        '"errors":[t.id() for t,_ in r.errors],'
        '"imports_failed":[t.id() for t,_ in r.errors if t.__class__.__name__=="_FailedTest"],'
        '"skipped":[t.id() for t,_ in r.skipped]}; '
        'pathlib.Path("baseline-result.json").write_text(json.dumps(d)); '
        'raise SystemExit(1 if r.wasSuccessful() or d["imports_failed"] or d["skipped"] else 0)'
    )
    completed = subprocess.run([sys.executable, '-B', '-c', code], env=env)
    baseline = json.loads(Path('baseline-result.json').read_text())
    baseline['sources'] = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in sources}
    report['results']['baseline'] = baseline
    if completed.returncode or baseline['tests'] != args.count:
        raise RuntimeError('Baseline did not produce a complete, discriminating native regression run')
    print('VERIFIED: native candidate tests pass and original baseline fails')
finally:
    Path('validation-result.json').write_text(json.dumps(report, indent=2))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as out:
            out.write(f'Candidate `{candidate_sha}` against `{args.base}`\n\n')
            out.write('```json\n' + json.dumps(report, indent=2) + '\n```\n')
