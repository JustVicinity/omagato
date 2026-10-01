#!/usr/bin/env bash
# Restrict operations to expected managed leaves and reject symlink ancestors.
guard_managed_path() {
  python3 - "$1" "$2" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
if not path.is_absolute() or '..' in path.parts or len(path.parts) < 4 or path.name != sys.argv[2]:
    sys.exit('Refusing unsafe managed path')
for candidate in (path, *path.parents):
    if candidate.is_symlink():
        sys.exit('Refusing a symlink in managed path: ' + str(candidate))
    if candidate.exists() and candidate != path and not candidate.is_dir():
        sys.exit('Refusing non-directory path ancestor')
PY
}
