"""Run each test module separately: legacy modules alter sys.path globally."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
env = dict(os.environ)
env["PYTHONPATH"] = os.pathsep.join([str(root / "agent_123_domotique"), str(root), env.get("PYTHONPATH", "")])
failed = []
for test in sorted((root / "tests").glob("test_*.py")):
    result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", test.name], cwd=root, env=env)
    print(f"{test.name}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
    if result.returncode:
        failed.append(test.name)
print(f"Failed modules: {failed}")
sys.exit(bool(failed))
