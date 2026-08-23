import json
from pathlib import Path
import tempfile
import unittest

from walden_list.build import BuildError, build_lists, validate_distribution


def source_config() -> dict:
    return {
        "repository": "https://example.invalid/source.git",
        "ref": "main",
        "homepage": "https://example.invalid/source",
        "license": "MIT",
    }


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_a = self.root / "source-a"
        self.source_b = self.root / "source-b"
        self.source_a.mkdir()
        self.source_b.mkdir()
        (self.source_a / "hosts").write_text(
            "0.0.0.0 a.example\n0.0.0.0 shared.example\n", encoding="utf-8"
        )
        (self.source_b / "block.txt").write_text(
            "b.example\nshared.example\n", encoding="utf-8"
        )
        (self.source_b / "allow.txt").write_text("b.example\n", encoding="utf-8")
        (self.source_b / "meta.json").write_text(
            json.dumps({"list": {"block": "block.txt", "allow": "allow.txt"}}),
            encoding="utf-8",
        )
        (self.root / "allow-local.txt").write_text("", encoding="utf-8")
        self.output = self.root / "dist" / "v1"

    def tearDown(self):
        self.temporary.cleanup()

    def config(self, strategy="union"):
        return {
            "schema_version": 1,
            "settings": {"max_category_change_percent": 35},
            "sources": {"source-a": source_config(), "source-b": source_config()},
            "categories": [
                {
                    "id": "example",
                    "name": "Example",
                    "description": "Fixture category",
                    "strategy": strategy,
                    "inputs": [
                        {"source": "source-a", "path": "hosts", "format": "hosts"},
                        {
                            "source": "source-b",
                            "path_from_json": "meta.json",
                            "json_key": "list.block",
                            "format": "domains",
                        },
                    ],
                    "excludes": [
                        {
                            "source": "source-b",
                            "path_from_json": "meta.json",
                            "json_key": "list.allow",
                            "format": "domains",
                        }
                    ],
                    "curation": {"allowlist": "allow-local.txt"},
                }
            ],
        }

    def build(self, config=None, allow_large_change=False):
        return build_lists(
            config or self.config(),
            self.root,
            self.output,
            {"source-a": self.source_a, "source-b": self.source_b},
            allow_large_change,
        )

    def test_union_build_is_deterministic_and_valid(self):
        first = self.build()
        first_files = {
            path.relative_to(self.output): path.read_bytes()
            for path in self.output.rglob("*")
            if path.is_file()
        }
        second = self.build()
        second_files = {
            path.relative_to(self.output): path.read_bytes()
            for path in self.output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(first_files, second_files)
        self.assertEqual(first, second)
        self.assertEqual(
            (self.output / "categories/example.txt").read_text(encoding="utf-8"),
            "a.example\nshared.example\n",
        )
        validate_distribution(self.output)

    def test_intersection_keeps_only_shared_domains(self):
        manifest = self.build(self.config(strategy="intersection"))
        self.assertEqual(manifest["categories"]["example"]["domains"], 1)
        self.assertEqual(
            (self.output / "categories/example.txt").read_text(encoding="utf-8"),
            "shared.example\n",
        )

    def test_category_can_use_a_custom_project_file(self):
        (self.root / "custom.txt").write_text("custom.example\n", encoding="utf-8")
        config = self.config()
        config["categories"][0]["inputs"] = [
            {"project_path": "custom.txt", "format": "domains"}
        ]
        config["categories"][0]["excludes"] = []
        manifest = self.build(config)
        self.assertEqual(manifest["categories"]["example"]["domains"], 1)
        self.assertEqual(
            (self.output / "categories/example.txt").read_text(encoding="utf-8"),
            "custom.example\n",
        )

    def test_validation_detects_tampering(self):
        self.build()
        (self.output / "categories/example.txt").write_text(
            "tampered.example\n", encoding="utf-8"
        )
        with self.assertRaises(BuildError):
            validate_distribution(self.output)

    def test_large_count_change_requires_override(self):
        self.build()
        (self.source_a / "hosts").write_text(
            "0.0.0.0 changed.example\n", encoding="utf-8"
        )
        (self.source_b / "block.txt").write_text(
            "changed.example\n", encoding="utf-8"
        )
        with self.assertRaises(BuildError):
            self.build()
        self.build(allow_large_change=True)


if __name__ == "__main__":
    unittest.main()
