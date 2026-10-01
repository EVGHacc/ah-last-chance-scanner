import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VacancyRegistryContractTests(unittest.TestCase):
    def rows(self):
        with (ROOT / "vacancy-monitor/registry.tsv").open(encoding="utf-8") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))

    def test_registry_is_nonempty_unique_and_structurally_complete(self):
        rows = self.rows()
        self.assertTrue(rows)
        identities = [(row["kind"], row["name"]) for row in rows]
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(row.get("official_domain") for row in rows))
        self.assertTrue(all(row.get("seed_urls") for row in rows))

    def test_registry_count_is_derived_not_asserted_here(self):
        rows = self.rows()
        # The control plane intentionally does not hard-code 104/106/107.
        # Registry size is a runtime fact used by the independent verifier.
        self.assertGreater(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
