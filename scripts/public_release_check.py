"""Check the repository before a first public GitHub release.

This is deliberately read-only. It checks the checkout and public-facing files,
but never creates a tag, pushes a branch, or contacts GitHub.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REQUIRED_FILES = (
    "README.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
    ".github/workflows/ci.yml",
    ".github/workflows/build-windows.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
)
GENERATED_PREFIXES = ("build-out/", "output/", "ui/dist/", "node_modules/", ".venv/")
TEXT_SUFFIXES = {".md", ".txt", ".py", ".ps1", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".json", ".yml", ".yaml"}
SCAN_EXCLUDES = {"scripts/public_release_check.py"}
PERSONAL_PATH_PATTERNS = (
    re.compile(r"(?i)[a-z]:[\\/]users[\\/][^\\/\s`]+"),
    re.compile(r"(?i)[a-z]:[\\/]图库(?:[\\/]|$)"),
    re.compile(r"(?i)gallery-project-backups"),
    re.compile(r"(?i)(?:^|[\\/])Users[\\/][^\\/\s`]+"),
)


def git_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return sorted(name for name in result.stdout.decode("utf-8").split("\0") if name)


def is_generated(name: str) -> bool:
    return name.startswith(GENERATED_PREFIXES) or name in {"runtime.local.json", "GalleryTool.local.json"}


def scan_text(root: Path, names: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for name in names:
        path = root / name
        if (
            name in SCAN_EXCLUDES
            or is_generated(name)
            or not path.is_file()
            or path.suffix.lower() not in TEXT_SUFFIXES
            or path.stat().st_size > 2_000_000
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PERSONAL_PATH_PATTERNS):
                findings.append({"path": name, "line": str(line_number)})
    return findings


def check(root: Path) -> dict:
    names = git_files(root)
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    generated = [name for name in names if is_generated(name)]
    personal_paths = scan_text(root, names)
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    remote = subprocess.run(
        ["git", "remote"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    workflows = [name for name in names if name.startswith(".github/workflows/")]
    report = {
        "required_files": {"missing": missing, "passed": not missing},
        "personal_paths": {"findings": personal_paths, "passed": not personal_paths},
        "generated_files": {"files": generated, "passed": not generated},
        "development_metadata": {
            "release_channel": package.get("releaseChannel"),
            "release_label": package.get("releaseLabel"),
            "version": package.get("version"),
            "passed": package.get("releaseChannel") == "development"
            and package.get("releaseLabel") == "开发预览（未发布）"
            and package.get("version") == "0.0.0-dev",
        },
        "workflows": {"files": workflows, "passed": len(workflows) >= 2},
        "external": {
            "git_remote_configured": bool(remote),
            "github_repository_created": None,
            "ci_passed": None,
            "release_published": None,
            "code_signed": None,
        },
    }
    report["passed"] = all(
        section["passed"]
        for section in report.values()
        if isinstance(section, dict) and "passed" in section
    )
    # This offline check cannot establish remote CI, package acceptance or publication.
    report["publish_ready"] = None if report["passed"] and remote else False
    return report


def configure_output() -> None:
    """Keep Chinese diagnostics printable on Windows runners using cp1252."""
    stream = getattr(sys, "stdout", None)
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def main() -> int:
    configure_output()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()
    report = check(args.root.resolve())
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    headline = "LOCAL_CHECK_PASS" if report["passed"] else "LOCAL_CHECK_BLOCKED"
    if not report["external"]["git_remote_configured"]:
        headline += "; PUBLISH_BLOCKED_EXTERNAL_SETUP"
    else:
        headline += "; EXTERNAL_CHECKS_REQUIRED"
    print(encoded if args.json else headline + "\n" + encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
