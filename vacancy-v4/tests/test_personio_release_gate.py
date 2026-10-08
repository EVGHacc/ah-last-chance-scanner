"""Run mandatory Personio release suites through existing root CI discovery.

This bridges tests/unit into the existing provider workflow without editing
privileged GitHub Actions workflow files or weakening release checks.
"""
import unittest

MANDATORY = (
    "test_personio.py",
    "test_personio_batch.py",
    "test_promote_personio_artifact.py",
    "test_proof_acceptance.py",
    "test_certification_registry.py",
    "test_release_gate.py",
)


class PersonioReleaseGate(unittest.TestCase):
    def test_required_unit_contract_and_promotion_suites(self):
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for filename in MANDATORY:
            suite.addTests(loader.discover(start_dir="tests/unit", pattern=filename,
                                           top_level_dir="tests/unit"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        self.assertGreater(result.testsRun, 0, "No release tests were discovered")
        self.assertTrue(result.wasSuccessful(), "Personio release suite failed")
