"""Build a Vite release and atomically switch the nginx document root."""

from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def publish(web_root: Path, font_file: Path | None = None) -> Path:
    font_data = None
    if font_file is not None:
        font_data = font_file.read_bytes()
        if not font_data.startswith(b"wOF2"):
            raise ValueError(f"Expected a WOFF2 font: {font_file}")

    frontend = Path(__file__).resolve().parents[1] / "frontend"
    releases = web_root / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    release = Path(tempfile.mkdtemp(prefix="release-", dir=releases))
    try:
        release.chmod(0o755)
        subprocess.run(["npm", "ci"], cwd=frontend, check=True)
        subprocess.run(
            ["npm", "run", "build", "--", "--outDir", str(release), "--emptyOutDir"],
            cwd=frontend,
            check=True,
        )
        for required in ("index.html", "cars/index.html"):
            if not (release / required).is_file():
                raise RuntimeError(f"Frontend build did not produce {required}")

        if font_data is not None:
            (release / "fonts" / "site.woff2").write_bytes(font_data)

        # Keep fingerprinted files reachable by tabs opened before this release.
        for asset in (release / "assets").rglob("*"):
            if not asset.is_file():
                continue
            shared = web_root / asset.relative_to(release)
            shared.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(asset, shared)
            except FileExistsError:
                pass

        with tempfile.TemporaryDirectory(prefix=".switch-", dir=web_root) as pending:
            next_link = Path(pending) / "current"
            next_link.symlink_to(release.relative_to(web_root), target_is_directory=True)
            os.replace(next_link, web_root / "current")
    except BaseException:
        if (web_root / "current").resolve() != release:
            shutil.rmtree(release)
        raise
    return release


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web-root", type=Path, required=True)
    parser.add_argument("--font-file", type=Path, help="WOFF2 font to use for the EV98 interface")
    args = parser.parse_args()
    web_root = args.web_root.resolve()
    web_root.mkdir(parents=True, exist_ok=True)
    with (web_root / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        print(publish(web_root, args.font_file))
