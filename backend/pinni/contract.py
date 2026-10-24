"""The JSON Schemas in contract/ are the single source of truth: request bodies are validated
against them directly instead of being copied into Pydantic models."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import ApiError


class Contract:
    def __init__(self, contract_dir: Path):
        self.dir = contract_dir
        schemas = {
            p.name: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((contract_dir / "schemas").glob("*.schema.json"))
        }
        if not schemas:
            raise RuntimeError(f"No schemas found in {contract_dir / 'schemas'}")
        self.registry = Registry().with_resources(
            (name, Resource.from_contents(s)) for name, s in schemas.items()
        )
        self._validators: dict[str, Draft202012Validator] = {}

    def validator(self, ref: str) -> Draft202012Validator:
        """`ref` is e.g. 'story.schema.json' or 'channel.schema.json#/$defs/Post'."""
        if ref not in self._validators:
            self._validators[ref] = Draft202012Validator(
                {"$ref": ref}, registry=self.registry, format_checker=FormatChecker()
            )
        return self._validators[ref]

    def errors(self, ref: str, doc) -> list[str]:
        out = []
        for err in self.validator(ref).iter_errors(doc):
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            out.append(f"{where}: {err.message}")
        return out

    def check(self, ref: str, doc) -> None:
        """Raise a 422 if `doc` does not match the schema."""
        problems = self.errors(ref, doc)
        if problems:
            raise ApiError(422, "invalid", "; ".join(problems[:5]))

    def mock(self, name: str):
        return json.loads((self.dir / "mock" / name).read_text(encoding="utf-8"))
