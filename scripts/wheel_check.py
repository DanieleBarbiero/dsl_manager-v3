"""Install a wheel into a fresh directory and exercise it outside the source tree."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dslm3.common import dump_json, now

parser = argparse.ArgumentParser()
parser.add_argument("--wheel", type=Path, required=True)
parser.add_argument("--report", type=Path, default=Path("reports/wheel_result.json"))
args = parser.parse_args()
wheel = args.wheel.resolve()
with tempfile.TemporaryDirectory(prefix="dslm3_wheel_") as temporary:
    root = Path(temporary)
    target = root / "installed"
    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheel),
        ],
        capture_output=True,
        text=True,
    )
    if install.returncode:
        raise RuntimeError(install.stdout + install.stderr)
    code = """
import json,os
from pathlib import Path
import dslm3
from dslm3.service import Application
from dslm3.web import create_app,dispatch
from dslm3.exports import Exports
from fastapi.testclient import TestClient
assert Path(dslm3.__file__).is_relative_to(Path(os.environ['PYTHONPATH']))
base=Path(dslm3.__file__).parent
assert (base/'static/app.js').is_file()
assert (base/'resources/gexf/gexf.xsd').is_file()
assert len([p for p in (base/'resources/vega').rglob('*') if p.is_file()])==6
app=Application('fresh_workspace');app.load_vega()
dispatch(app,'config',{'profile':'conservative'})
result=dispatch(app,'pipeline',{})
assert result['parse']['success']==6 and result['errors']==0
snapshot=Exports(app).snapshot();graph=Exports(app).graph(snapshot['id'])
with TestClient(create_app('fresh_workspace')) as client:
    assert client.get('/').status_code==200
    assert client.get('/static/app.js').status_code==200
print(json.dumps({'status':'passed','import_path':str(base),'sources':6,'snapshot_counts':snapshot['counts'],'graph_validation':graph['validation'],'static_resources':True,'outside_source_tree':True}))
"""
    env = {**os.environ, "PYTHONPATH": str(target)}
    run = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if run.returncode:
        dump_json(
            args.report,
            {"status": "failed", "stdout": run.stdout, "stderr": run.stderr},
        )
        raise SystemExit(run.returncode)
    result = json.loads(run.stdout.strip().splitlines()[-1])
    dump_json(args.report, {**result, "timestamp": now(), "wheel": wheel.name})
    print(json.dumps(result, indent=2))
