from __future__ import annotations

import json
from pathlib import Path


class MockDialer:
    def __init__(self, path: Path):
        self.path = Path(path)

    def loaded_refs(self) -> set[str]:
        if not self.path.exists():
            return set()
        return {json.loads(l)["crm_contact_id"] for l in self.path.read_text().splitlines() if l}

    def push(self, task_name: str, record: dict) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps({"task": task_name, **record}) + "\n")
