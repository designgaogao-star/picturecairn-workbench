"""Export contracts without starting workers or touching a user's catalog."""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gallery.app import create_app  # noqa: E402
from gallery.paths import Settings  # noqa: E402


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as temporary:
        app = create_app(Settings(Path(temporary), watch=False, scan_on_start=False))
        schema = app.openapi()
        (root / 'contracts' / 'openapi.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
