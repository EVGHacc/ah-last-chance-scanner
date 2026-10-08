"""Run Breezy unit/contract suites from the existing root CI discovery."""
import unittest


class BreezyReleaseGate(unittest.TestCase):
    def test_breezy_unit_and_contract_suites(self):
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for name in ("test_breezy.py", "test_breezy_batch.py"):
            suite.addTests(loader.discover(start_dir="tests/unit", pattern=name,
                                           top_level_dir="tests/unit"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        self.assertEqual(result.testsRun, 9)
        self.assertTrue(result.wasSuccessful())
