"""Turn raw Claude Code project directory names into readable, safe labels.

Claude Code encodes a session's working directory into the project directory
name by replacing every path separator with a dash, so ``/Users/alice/code``
becomes ``-Users-alice-code``. Those names leak the account name and read
badly.

A dash inside a directory name is indistinguishable from a separator once
encoded, so the real ``cwd`` recorded in the transcript is used when available
and the dash form is only a fallback. Either way the result goes through the
redactor, so anything the decoding misses is still masked.
"""

from typing import Optional

from ._vendor.redactor import redact_text

HOME_MARKERS = ("Users", "home")
TAIL_SEGMENTS = 2
FALLBACK_TOKENS = 3
HOME_LABEL = "~"


def _from_path(cwd: str) -> str:
    """Last few components of a real working directory, home prefix removed."""
    parts = [part for part in str(cwd).replace("\\", "/").split("/") if part]
    if len(parts) >= 2 and parts[0] in HOME_MARKERS:
        parts = parts[2:]
    if not parts:
        return HOME_LABEL
    return "-".join(parts[-TAIL_SEGMENTS:])


def _from_dashes(name: str) -> str:
    """Fallback decode for a dash-encoded name with no working directory."""
    parts = [part for part in name.split("-") if part]
    if parts and parts[0] in HOME_MARKERS:
        # Drop the marker and the token after it, which starts the account
        # name. An account name may hold further dashes that cannot be told
        # apart from separators here; the caller's redactor pass covers those.
        parts = parts[2:]
    if not parts:
        return HOME_LABEL
    return "-".join(parts[-FALLBACK_TOKENS:])


def pretty(name: str, cwd: Optional[str] = None, redact: bool = True) -> str:
    """Display label for a project directory."""
    if not redact:
        return name
    if cwd:
        label = _from_path(cwd)
    else:
        # Redact before splitting: an account name may contain dashes, and
        # splitting first would destroy the token the redactor looks for.
        label = _from_dashes(redact_text(name))
    return redact_text(label) or HOME_LABEL


def pretty_path(path: object, redact: bool = True) -> str:
    """Mask a filesystem path before it appears in a message to the user."""
    text = str(path)
    return redact_text(text) if redact else text
