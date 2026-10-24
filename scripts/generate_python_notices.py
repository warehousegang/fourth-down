"""Inventory the pinned local environment without importing or executing packages."""
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
text = ["FOURTH DOWN — PYTHON DEPENDENCY NOTICES\n\n"
        "Installed distributions matching requirements-lock.txt. Python packages and\n"
        "their binaries are not redistributed in the static frontend or source tree.\n"
        "These complete installed license/notice files are retained for review.\n"
        "Do not treat this inventory as permission to bundle future binary releases.\n"]
inventory = []
for requirement in (ROOT / "requirements-lock.txt").read_text().splitlines():
    name, version = requirement.split("==")
    dist = metadata.distribution(name)
    assert dist.version == version, f"Version mismatch: {name}"
    files = sorted(f for f in dist.files or [] if ".dist-info/" in str(f) and any(
        word in str(f).lower() for word in ("license", "notice", "copying")))
    entries = []
    text.append(f"\n{'=' * 72}\n{name}=={version}\nhttps://pypi.org/project/{name}/{version}/\n")
    sources = [(str(f), dist.locate_file(f)) for f in files]
    if name == "nflreadpy" and not sources:
        sources = [("https://github.com/nflverse/nflreadpy/blob/95b6cb50852523d043b8bf3abc62e801a3654b7d/LICENSE.md",
                    ROOT / "docs/licenses/nflreadpy-0.1.5-LICENSE.txt")]
    assert sources, f"No full notice available: {name}"
    for source, path in sources:
        raw = path.read_bytes()
        text.append(f"\nSource: {source}\n\n{raw.decode('utf-8').strip()}\n")
        entries.append({"source": source, "sha256": hashlib.sha256(raw).hexdigest()})
    inventory.append({"name": name, "version": version, "files": entries})
outputs = {
    "docs/PYTHON_DEPENDENCY_NOTICES.txt": "".join(text),
    "docs/PYTHON_DEPENDENCY_LICENSES.json": json.dumps(inventory, indent=2) + "\n",
}
for name, content in outputs.items():
    path = ROOT / name
    if "--check" in sys.argv:
        assert path.read_text() == content, f"Stale notice inventory: {name}"
    else:
        path.write_text(content)
print(f"{'Verified' if '--check' in sys.argv else 'Generated'} notices for {len(inventory)} pinned Python distributions")
