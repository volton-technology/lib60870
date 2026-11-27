#!/usr/bin/env python3
"""Fail when a workflow asks for a GitHub-hosted runner.

CI runs only on our self-hosted ARC runners (label volton-arc-production),
never on GitHub-hosted ones, on principle. Stdlib only, so it runs anywhere.

A `runs-on` must be an ARC or self-hosted label. A `${{ }}` expression is
allowed only when the workflow names no GitHub-hosted label anywhere, so a
matrix or input cannot resolve to one. Reusable-workflow `runs-on` inputs
are checked where the caller sets them.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HOSTED = re.compile(
    r"(?<![\w.-])(?:ubuntu|macos|windows)-(?:latest|slim|\d[\w.-]*)(?![\w])"
    r"|(?<![\w.-])blacksmith-[\w-]+|(?<![\w.-])(?:depot|namespace|warp|buildjet)-[\w-]+-(?:ubuntu|linux|macos)[\w-]*"
)
ALLOWED = re.compile(r"^(?:volton-arc[\w-]*|self-hosted)$")
RUNS_ON = re.compile(r"^(\s*)(?:-\s+)?runs-on:\s*(.*?)\s*$")


def strip_comment(line: str) -> str:
    """Return the line without a trailing YAML comment."""
    return re.sub(r"\s+#.*$", "", line)


def labels(lines: list[str], start: int, indent: int, inline: str) -> list[str]:
    """Return the label tokens of the runs-on whose key is on line `start`."""
    if inline:
        if "${{" in inline:
            return [inline]
        return re.findall(r"[^\s,\[\]'\"]+", inline)
    found = []
    for line in lines[start + 1 :]:
        stripped = strip_comment(line).rstrip()
        if not stripped.strip():
            continue
        if len(stripped) - len(
            stripped.lstrip()
        ) <= indent and not stripped.lstrip().startswith("- "):
            break
        item = stripped.strip().lstrip("-").strip().strip("'\"")
        if item.startswith(("group:", "labels:")):
            continue
        if re.match(r"^[\w-]+:(\s|$)", item):
            return []  # a workflow_call input named runs-on, not a job's runner
        if item:
            found.append(item)
    return found


def check(path: Path) -> list[str]:
    """Return the problems in one workflow or action file."""
    lines = path.read_text().splitlines()
    code = [strip_comment(text) for text in lines]
    hosted_anywhere = any(HOSTED.search(text) for text in code)
    problems = []
    for number, line in enumerate(code):
        match = RUNS_ON.match(line)
        if not match:
            if HOSTED.search(line) and re.search(
                r"^\s*(?:-\s+)?(?:os|runner|runs-on|runner-label)s?:", line
            ):
                where = f"{path}:{number + 1}"
                problems.append(
                    f"{where}: GitHub-hosted label in a matrix: {line.strip()}"
                )
            continue
        found = labels(code, number, len(match.group(1)), match.group(2))
        if "self-hosted" in found:
            continue  # [self-hosted, linux, ...] selects only our own runners
        for label in found:
            if "${{" in label:
                if hosted_anywhere:
                    where = f"{path}:{number + 1}"
                    problems.append(
                        f"{where}: runs-on `{label}` in a workflow that names a hosted label"
                    )
            elif not ALLOWED.match(label):
                where = f"{path}:{number + 1}"
                problems.append(
                    f"{where}: runs-on `{label}` is not an ARC or self-hosted label"
                )
    return problems


def main() -> int:
    """Check every workflow and action under the given root."""
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    github = root / ".github"
    files = sorted(github.glob("workflows/*.y*ml"))
    files += sorted(github.glob("actions/**/action.y*ml"))
    problems = [p for f in files for p in check(f)]
    for problem in problems:
        print(problem)
    if problems:
        print(
            "CI runs only on self-hosted ARC runners, never GitHub-hosted: "
            "use `runs-on: volton-arc-production`."
        )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
