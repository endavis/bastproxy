#!/usr/bin/env python3
"""Claude Code PreToolUse hook to block dangerous command patterns.

This hook intercepts Bash commands before execution and blocks those
containing dangerous flags that could bypass security controls.

Uses shlex to properly parse shell quoting, then checks for dangerous
patterns as standalone tokens (not embedded in quoted argument values).

Exit codes:
  0 - Allow command
  2 - Block command (shows stderr to Claude)

For full documentation, see: docs/development/ai/command-blocking.md
"""

import json
import shlex
import subprocess  # nosec B404 - needed for git branch detection
import sys

# Protected branches - operations on these require extra scrutiny
PROTECTED_BRANCHES = {"main", "master"}

# Dangerous flags that must appear as exact standalone tokens
DANGEROUS_FLAGS = {
    "--admin": "Bypasses branch protection rules",
    "--no-verify": "Skips pre-commit/pre-push hooks",
    "--hard": "Hard reset - can lose uncommitted changes",
}

# Dangerous token sequences (checked in order)
# Format: (token_sequence, description)
DANGEROUS_SEQUENCES = [
    (["rm", "-rf", "/"], "Destructive: removes root filesystem"),
    (["rm", "-rf", "~"], "Destructive: removes home directory"),
    (["sudo", "rm"], "Privileged deletion"),
]

# Force push flags
FORCE_PUSH_FLAGS = {"--force", "-f", "--force-with-lease"}

# Blocked workflow commands - use doit wrappers or require user approval
BLOCKED_WORKFLOW_COMMANDS = {
    (
        "gh",
        "issue",
        "create",
    ): "Use 'doit issue --type=<type>' instead of 'gh issue create'",
    ("gh", "pr", "create"): "Use 'doit pr' instead of 'gh pr create'",
    ("gh", "pr", "merge"): "Use 'doit pr_merge' instead of 'gh pr merge'",
    ("uv", "add"): (
        "Adding dependencies requires user approval. "
        "Suggest the package and let the user run 'uv add <package>' manually."
    ),
    ("doit", "release"): (
        "Releases must be run manually by the user, not by AI agents. "
        "AI can help prepare (update changelog, verify CI) but not execute releases."
    ),
    (
        "doit",
        "release_dev",
    ): "Releases must be run manually by the user, not by AI agents.",
    (
        "doit",
        "release_tag",
    ): "Releases must be run manually by the user, not by AI agents.",
    (
        "doit",
        "release_pr",
    ): "Releases must be run manually by the user, not by AI agents.",
}

# Governance labels that require human approval - AI should never add these
GOVERNANCE_LABELS = {
    "ready-to-merge": (
        "The 'ready-to-merge' label is a governance control requiring human approval. "
        "Add this label manually via 'gh pr edit --add-label ready-to-merge' or the GitHub web UI."
    ),
}


def tokenize(command: str) -> list[str]:
    """Tokenize command using shlex for proper shell quote handling.

    shlex.split() correctly handles:
    - Double quoted strings: "text with --admin"
    - Single quoted strings: 'text with --force'
    - Embedded quotes: --body="value"
    - Escape sequences

    Returns list of tokens with quotes stripped from values.
    """
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        # Fallback for malformed quotes - try non-POSIX mode
        try:
            return shlex.split(command, posix=False)
        except ValueError:
            # Last resort - simple whitespace split
            return command.split()


def check_dangerous_flags(tokens: list[str]) -> tuple[bool, str]:
    """Check if any dangerous flag appears as a standalone token.

    A flag in a quoted argument value (e.g., -m "--admin mentioned")
    becomes part of a larger token and won't match.
    """
    for token in tokens:
        if token in DANGEROUS_FLAGS:
            return True, DANGEROUS_FLAGS[token]
    return False, ""


def check_dangerous_sequences(tokens: list[str]) -> tuple[bool, str]:
    """Check if dangerous token sequences appear in the command.

    Looks for consecutive tokens matching dangerous patterns.
    """
    tokens_lower = [t.lower() for t in tokens]

    for sequence, reason in DANGEROUS_SEQUENCES:
        seq_len = len(sequence)
        for i in range(len(tokens_lower) - seq_len + 1):
            if tokens_lower[i : i + seq_len] == [s.lower() for s in sequence]:
                return True, reason
    return False, ""


def check_force_push_to_protected(tokens: list[str]) -> tuple[bool, str]:
    """Check if command is a force push to a protected branch.

    Allows force push to feature branches but blocks force push to main/master.
    If no branch is specified, blocks by default (safer).
    """
    tokens_lower = [t.lower() for t in tokens]

    # Must be a git push command
    if "git" not in tokens_lower or "push" not in tokens_lower:
        return False, ""

    # Check if any force flag is present
    has_force_flag = any(flag in tokens for flag in FORCE_PUSH_FLAGS)
    if not has_force_flag:
        return False, ""

    # Find the push index to look for branch/remote after it
    try:
        push_idx = tokens_lower.index("push")
    except ValueError:
        return False, ""

    # Look for protected branch name in tokens after 'push'
    # Skip flags (tokens starting with -)
    after_push = [t for t in tokens[push_idx + 1 :] if not t.startswith("-")]

    # Check if any token after push is a protected branch
    for token in after_push:
        # Handle origin/main format
        branch = token.split("/")[-1] if "/" in token else token

        if branch.lower() in PROTECTED_BRANCHES:
            return True, f"Force push to protected branch '{branch}'"

    # If no branch specified, block by default (could push to current branch = main)
    if not after_push or (len(after_push) == 1 and after_push[0] == "origin"):
        return (
            True,
            "Force push without explicit branch (could affect protected branch)",
        )

    return False, ""


def check_delete_protected_branch(tokens: list[str]) -> tuple[bool, str]:
    """Check if command deletes a protected branch (local or remote).

    Catches:
    - git push origin --delete main
    - git push origin :main
    - git branch -D main
    - git branch -d main
    """
    tokens_lower = [t.lower() for t in tokens]

    # Check for remote branch deletion: git push origin --delete main
    if "git" in tokens_lower and "push" in tokens_lower and "--delete" in tokens_lower:
        for token in tokens:
            if token.lower() in PROTECTED_BRANCHES:
                return True, f"Deleting protected remote branch '{token}'"

    # Check for remote branch deletion with colon syntax: git push origin :main
    if "git" in tokens_lower and "push" in tokens_lower:
        for token in tokens:
            if token.startswith(":") and token[1:].lower() in PROTECTED_BRANCHES:
                return True, f"Deleting protected remote branch '{token[1:]}'"

    # Check for local branch deletion: git branch -D main or git branch -d main
    if (
        "git" in tokens_lower
        and "branch" in tokens_lower
        and ("-d" in tokens_lower or "-D" in tokens)
    ):
        for token in tokens:
            if token.lower() in PROTECTED_BRANCHES:
                return True, f"Deleting protected local branch '{token}'"

    return False, ""


def get_current_branch() -> str | None:
    """Get the current git branch name.

    Returns None if not in a git repository or in detached HEAD state.
    """
    try:
        result = subprocess.run(  # nosec B603 B607 - trusted git command
            ["git", "branch", "--show-current"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def check_blocked_workflow_commands(tokens: list[str]) -> tuple[bool, str]:
    """Check if command uses blocked workflow commands.

    These commands should use doit wrappers instead of direct gh commands.
    """
    tokens_lower = [t.lower() for t in tokens]

    for cmd_tuple, reason in BLOCKED_WORKFLOW_COMMANDS.items():
        cmd_len = len(cmd_tuple)
        if len(tokens_lower) >= cmd_len and tuple(tokens_lower[:cmd_len]) == cmd_tuple:
            return True, reason
    return False, ""


def check_governance_labels(tokens: list[str]) -> tuple[bool, str]:
    """Check if command attempts to add a governance label.

    Governance labels (like 'ready-to-merge') require human approval and
    should never be added by AI agents.
    """
    tokens_lower = [t.lower() for t in tokens]

    # Check for: gh pr edit --add-label <governance-label>
    # or: gh issue edit --add-label <governance-label>
    if "gh" not in tokens_lower:
        return False, ""

    if "edit" not in tokens_lower:
        return False, ""

    if "--add-label" not in tokens_lower:
        return False, ""

    # Check if any governance label is being added
    for label, reason in GOVERNANCE_LABELS.items():
        if label.lower() in tokens_lower:
            return True, reason

    return False, ""


def check_merge_to_protected(tokens: list[str]) -> tuple[bool, str]:
    """Check if command is a merge that would create a merge commit on a protected branch.

    Protected branches often require linear history (no merge commits).
    Blocks `git merge` on protected branches unless --ff-only is specified.
    """
    tokens_lower = [t.lower() for t in tokens]

    # Must be a git merge command
    if "git" not in tokens_lower or "merge" not in tokens_lower:
        return False, ""

    # Allow if --ff-only is specified (fast-forward only, no merge commit)
    if "--ff-only" in tokens_lower:
        return False, ""

    # Check if we're on a protected branch
    current_branch = get_current_branch()
    if current_branch and current_branch.lower() in PROTECTED_BRANCHES:
        return True, (
            f"Merge on protected branch '{current_branch}' would create merge commit. "
            f"Use --ff-only for fast-forward merge, or merge via PR"
        )

    return False, ""


def check_command(command: str) -> tuple[bool, str]:
    """Check if command contains dangerous patterns.

    Uses shlex to tokenize, then checks for:
    1. Dangerous flags as standalone tokens
    2. Dangerous token sequences
    3. Force push to protected branches
    4. Deletion of protected branches
    5. Merge commits on protected branches
    6. Blocked workflow commands
    7. Governance labels

    Returns:
        (is_dangerous, reason)
    """
    tokens = tokenize(command)

    # Check for dangerous standalone flags
    is_dangerous, reason = check_dangerous_flags(tokens)
    if is_dangerous:
        return True, reason

    # Check for dangerous sequences
    is_dangerous, reason = check_dangerous_sequences(tokens)
    if is_dangerous:
        return True, reason

    # Check for force push to protected branches
    is_dangerous, reason = check_force_push_to_protected(tokens)
    if is_dangerous:
        return True, reason

    # Check for deletion of protected branches
    is_dangerous, reason = check_delete_protected_branch(tokens)
    if is_dangerous:
        return True, reason

    # Check for merge commits on protected branches
    is_dangerous, reason = check_merge_to_protected(tokens)
    if is_dangerous:
        return True, reason

    # Check for blocked workflow commands
    is_dangerous, reason = check_blocked_workflow_commands(tokens)
    if is_dangerous:
        return True, reason

    # Check for governance labels
    is_dangerous, reason = check_governance_labels(tokens)
    if is_dangerous:
        return True, reason

    return False, ""


def main() -> int:
    """Main entry point."""
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON input: {e}", file=sys.stderr)
        return 1

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    # Only check shell commands (Bash for Claude, run_shell_command for Gemini)
    if tool_name not in ("Bash", "run_shell_command"):
        return 0

    command = tool_input.get("command", "")
    if not command:
        return 0

    is_dangerous, reason = check_command(command)
    if is_dangerous:
        print(
            f"BLOCKED: Command contains dangerous pattern.\n"
            f"Reason: {reason}\n"
            f"Command: {command}\n"
            f"\n"
            f"If this is intentional, ask the user to run it manually.",
            file=sys.stderr,
        )
        return 2  # Exit 2 = Block and show stderr to Claude

    return 0


if __name__ == "__main__":
    sys.exit(main())
