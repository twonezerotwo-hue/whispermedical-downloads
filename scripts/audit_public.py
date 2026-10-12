"""Privacy audit of everything that is about to be published. Exit 1 (and a list) if anything private is found.

    python scripts/audit_public.py [folder]      default: the repository folder (every file except .git)

Looks for: API keys / tokens / private keys, personal absolute paths and the local user name, e-mail addresses (other than GitHub's no-reply), links to the
private source repository, recordings / transcripts / medical documents / model files, and files too big to be documentation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = {"scripts/audit_public.py", "tests/test_site_tools.py"}      # these name the patterns they look for
SKIP_DIRS = {".git", ".pytest_tmp", "__pycache__", "_build", "dist", "node_modules"}
BAD_SUFFIXES = {".mp4", ".m4a", ".mp3", ".wav", ".aiff", ".mov", ".mkv", ".flac", ".srt", ".vtt", ".bin", ".onnx", ".safetensors", ".pdf", ".docx", ".key", ".pem", ".pfx", ".p12", ".env"}
PATTERNS = {
    "token / key": re.compile(r"(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"),
    "personal path": re.compile(r"(?i)(c:\\users\\[a-z0-9_.-]+|/users/[a-z0-9_.-]+/|/home/[a-z0-9_.-]+/)"),
    "local user name": re.compile(r"(?<![A-Za-z0-9-])(twone|ADIN)(?![A-Za-z0-9-])"),
    "e-mail": re.compile(r"(?<![\w.-])[\w.+-]+@(?!users\.noreply\.github\.com)[\w-]+\.[\w.-]+"),
    "private source repo": re.compile(r"twonezerotwo-hue/whispermedical(?![-\w])|github\.com/twonezerotwo-hue/whispermedical(?![-\w])"),
}


def scan(root: Path) -> list[str]:
    problems = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel in SELF:
            continue
        if path.suffix.lower() in BAD_SUFFIXES or path.stat().st_size > 2_000_000:
            problems.append(f"{rel}: file type / size must not be published ({path.stat().st_size} bytes)")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            problems.append(f"{rel}: binary file")
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                problems.append(f"{rel}:{line}: {label}: {match.group(0)[:60]}")
    return problems


def main(argv=None) -> int:
    folder = Path((argv or sys.argv[1:] or [str(ROOT)])[0])
    problems = scan(folder)
    print("\n".join(problems) if problems else f"public audit: clean ({folder})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
