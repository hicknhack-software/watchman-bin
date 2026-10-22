"""Check a real daemon, watch registration, and incremental file discovery."""
import json
import pathlib
import subprocess
import tempfile
import time


with tempfile.TemporaryDirectory(prefix="watchman-smoke-") as directory:
    root = pathlib.Path(directory)
    sock = root / "sock"
    command = ["watchman", f"--sockname={sock}", f"--statefile={root / 'state'}",
               f"--logfile={root / 'log'}", "--log-level=2"]

    def request(*args):
        result = subprocess.run(command + ["-j"], input=json.dumps(args),
                                text=True, capture_output=True, check=True, timeout=30)
        response = json.loads(result.stdout)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response

    project = root / "project"
    project.mkdir()
    (project / ".watchmanconfig").write_text("{}")
    try:
        request("watch-project", str(project))
        clock = request("clock", str(project))["clock"]
        (project / "created.txt").write_text("watchman works\n")
        for _ in range(50):
            response = request("query", str(project), {
                "since": clock, "fields": ["name"],
                "expression": ["name", "created.txt"], "sync_timeout": 5000,
            })
            if "created.txt" in response["files"]:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError(f"New file was not detected: {response}")
        print("PASS: daemon startup, watch-project, clock, and incremental file query")
    finally:
        request("shutdown-server")
