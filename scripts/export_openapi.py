#!/usr/bin/env python3
"""Export OpenAPI spec for the TenantPlatform API."""

import json
from pathlib import Path

from api.main import create_app

out = Path(__file__).resolve().parents[1] / "openapi" / "identity-phase1.json"
out.parent.mkdir(parents=True, exist_ok=True)
schema = create_app().openapi()
out.write_text(json.dumps(schema, indent=2))
print(f"Wrote {out}")
