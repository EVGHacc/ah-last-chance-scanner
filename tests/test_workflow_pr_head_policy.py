"""Regression: synthetic PR merge must not include unrelated production snapshots."""
from pathlib import Path
import subprocess
import tempfile
import unittest


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


class PullRequestHeadPolicyTests(unittest.TestCase):
    def test_compare_immutable_pr_head_not_synthetic_merge(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, 'init', '-q', '-b', 'main')
            git(root, 'config', 'user.name', 'QA')
            git(root, 'config', 'user.email', 'qa@example.invalid')
            (root / 'README.md').write_text('baseline\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'baseline')
            base = git(root, 'rev-parse', 'HEAD')
            git(root, 'checkout', '-qb', 'feature')
            (root / 'scripts').mkdir()
            (root / 'tests').mkdir()
            (root / 'scripts' / 'recovery.py').write_text('print("hello")\n')
            (root / 'tests' / 'test_recovery.py').write_text('assert True\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'feature')
            head = git(root, 'rev-parse', 'HEAD')
            git(root, 'checkout', '-q', 'main')
            (root / 'data').mkdir()
            (root / 'data' / 'status.json').write_text('{"rawSeen":56}\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'live data bot')
            git(root, 'merge', '-q', '--no-ff', 'feature', '-m', 'synthetic PR merge')
            synthetic = git(root, 'rev-parse', 'HEAD')
            incorrect = git(root, 'diff', '--name-only', f'{base}...{synthetic}').splitlines()
            correct = git(root, 'diff', '--name-only', f'{base}...{head}').splitlines()
            self.assertIn('data/status.json', incorrect)
            self.assertEqual(correct, ['scripts/recovery.py', 'tests/test_recovery.py'])

    def test_workflow_uses_true_pr_head_in_both_jobs(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/engineering-quality.yml'
        source = path.read_text()
        self.assertGreaterEqual(source.count('github.event.pull_request.head.sha || github.sha'), 2)
        self.assertIn("base+'...'+head", source)
        self.assertIn('--head "$HEAD_SHA"', source)


if __name__ == '__main__':
    unittest.main()
