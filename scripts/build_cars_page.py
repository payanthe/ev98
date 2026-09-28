#!/usr/bin/env python3
"""Write the indexable imported-EV page from the vehicle catalog."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.cars_page import CONNECTOR_ICON_FILES, render_cars_page
from app.vehicles.catalog import load_catalog

ASSETS = ROOT / "frontend" / "src" / "assets"
PUBLIC = ROOT / "frontend" / "public"


def copy_icons() -> None:
    brand_out = PUBLIC / "brand-icons"
    brand_out.mkdir(parents=True, exist_ok=True)
    for path in (ASSETS / "brands").glob("*.svg"):
        shutil.copy2(path, brand_out / path.name)
    connector_out = PUBLIC / "connector-icons"
    connector_out.mkdir(parents=True, exist_ok=True)
    for file_name in CONNECTOR_ICON_FILES.values():
        shutil.copy2(ASSETS / "connectors" / file_name, connector_out / file_name)


def main() -> None:
    copy_icons()
    out = PUBLIC / "cars" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_cars_page(load_catalog()), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
