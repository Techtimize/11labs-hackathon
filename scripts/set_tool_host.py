"""Point agent/tools.json at a deployed host.

The six webhook tool definitions ship with a placeholder host. Editing them by hand is
six chances to publish one tool aimed at the wrong place, so do it in one step:

    python scripts/set_tool_host.py https://authrelay.example.com
    python scripts/set_tool_host.py --check          # fail if placeholders remain

Then upload agent/tools.json to the ElevenLabs agent.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "agent" / "tools.json"
PLACEHOLDER = "YOUR-HOST"
URL = re.compile(r"^https://([^/]+)(/tools/[a-z_]+)$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", help="Base URL, e.g. https://authrelay.example.com")
    parser.add_argument("--check", action="store_true", help="Only report whether a host is set")
    args = parser.parse_args()

    spec = json.loads(TOOLS.read_text(encoding="utf-8"))
    urls = [t["api_schema"]["url"] for t in spec["tools"]]

    if args.check or not args.host:
        unset = [u for u in urls if PLACEHOLDER in u]
        for u in urls:
            print(f"  {'PLACEHOLDER' if PLACEHOLDER in u else 'ok         '}  {u}")
        if unset:
            print(f"\n{len(unset)} of {len(urls)} tools still point at {PLACEHOLDER}.", file=sys.stderr)
            return 1
        print(f"\nAll {len(urls)} tools point at a host.")
        return 0

    host = args.host.rstrip("/")
    if not host.startswith("https://"):
        print("Host must start with https://, because the agent token travels on these calls.",
              file=sys.stderr)
        return 2

    for tool in spec["tools"]:
        match = URL.match(tool["api_schema"]["url"])
        if match is None:
            print(f"Unrecognised URL: {tool['api_schema']['url']}", file=sys.stderr)
            return 2
        tool["api_schema"]["url"] = host + match.group(2)

    TOOLS.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"Set {len(spec['tools'])} tool URLs to {host}. Re-upload agent/tools.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
