"""Write packages/openapi.json from the FastAPI app, no database needed (FR-96, FR-111)."""

import json
from pathlib import Path

from app.main import create_app

OUTPUT = Path(__file__).resolve().parents[3] / "packages" / "openapi.json"


def render_spec() -> str:
    spec = create_app().openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_spec(), encoding="utf-8")
    print(f"wrote {OUTPUT}")  # noqa: T201 - CLI output


if __name__ == "__main__":
    main()
