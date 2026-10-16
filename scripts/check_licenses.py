"""Fail when an installed dependency is not MIT, BSD, Apache-2.0, ISC, PSF or MPL-2.0 licensed.

Uses pip-licenses metadata; packages that publish no license metadata are classified from the LICENSE
file in their dist-info. Writes the full table to dist/licenses.json.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ALLOWED = re.compile(
    r"(\bMIT|\b0?BSD|\bApache|\bISC|\bPSF|Python Software Foundation|\bMPL-2\.0|Mozilla Public License 2\.0)",
    re.IGNORECASE,
)
FORBIDDEN = re.compile(r"\b(A?GPL|LGPL|SSPL|BUSL|Commons Clause|Proprietary|Commercial)\b", re.IGNORECASE)
IGNORE = {"evalgate", "toy-targets"}  # this repository (MIT)
ROOT = Path(__file__).resolve().parents[1]


def from_license_file(name: str) -> str:
    try:
        files = metadata.distribution(name).files or []
    except metadata.PackageNotFoundError:
        return "UNKNOWN"
    for f in files:
        if "licen" in f.name.lower() or "copying" in f.name.lower():
            text = (f.locate().read_text(errors="replace") if Path(str(f.locate())).is_file() else "")[:400]
            first = next((line.strip() for line in text.splitlines() if line.strip()), "")
            if first:
                return f"{first} (from {f.name})"
    return "UNKNOWN"


def main() -> int:
    raw = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--from=mixed", "--format=json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = json.loads(raw)
    bad = []
    for row in rows:
        if row["Name"] in IGNORE:
            continue
        lic = row["License"]
        if lic in ("UNKNOWN", "", "None"):
            lic = row["License"] = from_license_file(row["Name"])
        if FORBIDDEN.search(lic) and not ALLOWED.search(lic.split(" OR ")[0]):
            bad.append(row)
        elif not ALLOWED.search(lic):
            bad.append(row)
    out = ROOT / "dist" / "licenses.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rows, indent=2) + "\n")
    for row in bad:
        print(f"license not allowed: {row['Name']} {row['Version']}: {row['License']}", file=sys.stderr)
    print(f"licenses: {len(rows) - len(bad)}/{len(rows)} packages allowed; table in {out.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
