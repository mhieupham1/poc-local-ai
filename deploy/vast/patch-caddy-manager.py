from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch-caddy-manager.py /path/to/caddy_config_manager.py", file=sys.stderr)
        return 2

    target = Path(sys.argv[1])
    source = target.read_text()
    old = "subprocess.check_output([CADDY_BIN, 'hash-password', '-p', password])"
    new = "subprocess.check_output([CADDY_BIN, 'hash-password'], input=password.encode())"
    if source.count(old) != 1:
        print("refusing to patch: expected exactly one pinned hash-password call", file=sys.stderr)
        return 1

    target.write_text(source.replace(old, new))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
