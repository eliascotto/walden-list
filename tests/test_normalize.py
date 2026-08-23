import unittest

from walden_list.normalize import normalize_domain, parse_domain_lines, validate_output_domains


class NormalizeTests(unittest.TestCase):
    def test_normalizes_case_trailing_dot_and_idna(self):
        self.assertEqual(normalize_domain(" Example.COM. "), "example.com")
        self.assertEqual(normalize_domain("bücher.example"), "xn--bcher-kva.example")

    def test_rejects_non_hostnames(self):
        for value in (
            "localhost",
            "127.0.0.1",
            "https://example.com",
            "example.com/path",
            "bad-.example",
            "singlelabel",
            "*.example.com",
        ):
            with self.subTest(value=value):
                self.assertIsNone(normalize_domain(value))

    def test_parses_hosts_and_domain_lines(self):
        parsed = parse_domain_lines(
            [
                "# heading\n",
                "0.0.0.0 Example.com alias.example # note\n",
                "127.0.0.1 localhost\n",
                "bad value\n",
            ],
            "auto",
        )
        self.assertEqual(parsed.domains, {"example.com", "alias.example"})
        self.assertEqual(parsed.stats.rejected, 2)

    def test_output_requires_sorted_unique_domains(self):
        self.assertEqual(
            validate_output_domains(["a.example\n", "b.example\n"]),
            ["a.example", "b.example"],
        )
        with self.assertRaises(ValueError):
            validate_output_domains(["b.example\n", "a.example\n"])
        with self.assertRaises(ValueError):
            validate_output_domains(["a.example\n", "a.example\n"])


if __name__ == "__main__":
    unittest.main()

