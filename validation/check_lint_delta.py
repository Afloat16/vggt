import argparse
import collections
import json
import pathlib
import re
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--base", required=True)
parser.add_argument("--source", required=True)
parser.add_argument("--test", required=True)
args = parser.parse_args()
root = pathlib.Path.cwd()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"{command}: unexpected exit {result.returncode}: {result.stderr}")
    return result

def collect():
    shutil.rmtree(".mypy_cache", ignore_errors=True)
    lint = run(["ruff", "check", "--output-format", "json", "dinov3"])
    ruff = [(str(pathlib.Path(x["filename"]).relative_to(root)), x["code"], x["message"]) for x in json.loads(lint.stdout)]
    formatted = run(["ruff", "format", "--check", "dinov3"])
    format_files = re.findall(r"^Would reformat: (.+)$", formatted.stdout + formatted.stderr, re.MULTILINE)
    types = run(["mypy", "--txt-report", "."])
    mypy = []
    for line in (types.stdout + types.stderr).splitlines():
        match = re.match(r"^(.*?):\\d+(?::\\d+)?: error: (.*)$", line)
        if match:
            mypy.append((match.group(1), match.group(2)))
    if types.returncode and not mypy:
        raise RuntimeError("mypy failed without parsed diagnostics: " + types.stdout + types.stderr)
    return {"ruff": ruff, "format": format_files, "mypy": mypy}

subprocess.run(["ruff", "check", args.source, args.test], check=True)
subprocess.run(["ruff", "format", "--check", args.source, args.test], check=True)
candidate = collect()
subprocess.run(["git", "checkout", "--detach", args.base], check=True)
baseline = collect()
introduced = {}
for key in candidate:
    c = collections.Counter(tuple(x) if isinstance(x, list) else x for x in candidate[key])
    b = collections.Counter(tuple(x) if isinstance(x, list) else x for x in baseline[key])
    introduced[key] = list((c - b).elements())
summary = {
    "candidate": head,
    "baseline": args.base,
    "candidate_counts": {k: len(v) for k, v in candidate.items()},
    "baseline_counts": {k: len(v) for k, v in baseline.items()},
    "introduced": introduced,
    "targeted_ruff": "passed",
    "candidate_diagnostics": candidate,
    "baseline_diagnostics": baseline,
}
pathlib.Path("lint-delta.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({k: v for k, v in summary.items() if not k.endswith("_diagnostics")}, indent=2))
if any(introduced.values()):
    raise RuntimeError("new static-check diagnostics introduced by the candidate")
