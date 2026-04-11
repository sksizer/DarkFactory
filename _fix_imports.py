"""One-shot script to replace darkfactory.prd imports with darkfactory.model."""

import os
import re

root = "."
patterns = [
    (r"from darkfactory\.prd import", "from darkfactory.model import"),
    (r"from \.prd import", "from .model import"),
]

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", ".worktrees")]
    for fn in filenames:
        if not fn.endswith(".py"):
            continue
        fpath = os.path.join(dirpath, fn)
        with open(fpath, "r") as f:
            content = f.read()
        original = content
        for pat, rep in patterns:
            content = re.sub(pat, rep, content)
        if content != original:
            with open(fpath, "w") as f:
                f.write(content)
            print(f"Updated: {fpath}")
