"""Preserve upstream and Rust crate license notices alongside the binary bundle."""
import pathlib
import re
import shutil
import sys

paths_file, package = map(pathlib.Path, sys.argv[1:])
destination = package / "share/doc/watchman/third-party-licenses"
pattern = re.compile(r"^(licen[cs]es?|copying|copyright|notices?|patents?)([._-].*)?$", re.I)


def collect(name, source):
    if not source.is_dir():
        return
    for entry in source.iterdir():
        if pattern.match(entry.name):
            target = destination / name / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry.is_dir():
                shutil.copytree(entry, target, dirs_exist_ok=True)
            elif entry.is_file():
                shutil.copyfile(entry, target)


for line in paths_file.read_text().splitlines():
    key, _, value = line.partition("=")
    if key.endswith("_SOURCE"):
        collect(key.removesuffix("_SOURCE"), pathlib.Path(value))
for source in pathlib.Path("/scratch/cargo/registry/src").glob("*/*"):
    collect(f"rust/{source.name}", source)
for source in pathlib.Path("/scratch/source/watchman/thirdparty").glob("*"):
    collect(f"watchman-vendored/{source.name}", source)
