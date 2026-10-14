"""Run one test directory and print a JSON summary on the last line.

Used by co.py as a subprocess, so each suite gets a fresh interpreter and the
target implementation is imported from PYTHONPATH.
"""

import json
import sys
import unittest

sys.dont_write_bytecode = True


def main():
    start = sys.argv[1]
    loader = unittest.TestLoader()
    suite = loader.discover(start, pattern="*.py", top_level_dir=start)
    result = unittest.TestResult()
    suite.run(result)
    problems = result.failures + result.errors
    summary = {
        "run": result.testsRun,
        "failed": sorted(t.id() for t, _ in problems),
        "details": {t.id(): tb for t, tb in problems},
    }
    sys.stdout.write("\n" + json.dumps(summary) + "\n")


if __name__ == "__main__":
    main()
