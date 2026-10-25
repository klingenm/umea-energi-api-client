"""Patch known gaps in the upstream OpenAPI document before code generation.

The upstream document is produced by Swashbuckle (.NET) and has two problems that
break openapi-python-client:

- Properties that reference another schema are never marked nullable, but the API
  does return ``null`` for them (e.g. ``"error": null``). Every bare ``$ref``
  property is rewritten to ``allOf: [$ref]`` with ``nullable: true``.
- ``Newtonsoft.Json.Linq.JToken`` is a self-referential array that the generator
  cannot represent. It stands for arbitrary JSON, so it is replaced with ``{}``.

Usage: normalize_openapi.py <input> <output>
"""

import json
import sys
from pathlib import Path
from typing import Any

ANY_JSON_SCHEMAS = ["Newtonsoft.Json.Linq.JToken"]


def normalize(document: dict[str, Any]) -> dict[str, Any]:
    schemas: dict[str, Any] = document["components"]["schemas"]
    for name in ANY_JSON_SCHEMAS:
        if name in schemas:
            schemas[name] = {}
    for schema in schemas.values():
        properties: dict[str, Any] = schema.get("properties", {})
        for name, prop in properties.items():
            if set(prop) == {"$ref"}:
                properties[name] = {"allOf": [prop], "nullable": True}
    return document


def main() -> None:
    source, target = (Path(arg) for arg in sys.argv[1:3])
    document = normalize(json.loads(source.read_text(encoding="utf-8")))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
