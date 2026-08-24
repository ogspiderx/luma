#!/usr/bin/env python3
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def suites():
    names = [n for n in os.listdir(HERE)
             if n.startswith("test_") and n.endswith(".py")]
    return sorted(names)


def main():
    names = suites()
    failed = []
    for name in names:
        sys.stdout.write(f"{name:<40}")
        sys.stdout.flush()
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, name)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print("PASS")
        else:
            print("FAIL")
            failed.append((name, result.stdout + result.stderr))

    print()
    if not failed:
        print(f"{len(names)} suites passed")
        return 0
    for name, output in failed:
        print("=" * 62)
        print(name)
        print("=" * 62)
        for line in output.splitlines():
            if "FAIL" in line or "Error" in line:
                print(line)
    print(f"\n{len(failed)} of {len(names)} suites failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
