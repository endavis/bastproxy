# AI Agent Setup Guide

This template includes pre-configured settings for multiple AI coding assistants.

## Supported AI Agents

### 1. Codex CLI (OpenAI)

**Configuration:** `.codex/config.toml`

Codex CLI directly reads `AGENTS.md` from the project root. The configuration file whitelists common development commands.

**Whitelisted commands:**
- `git` - All git operations
- `gh` - GitHub CLI
- `uv` - UV package manager
- `doit` - Task automation
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Setup:**
```bash
# Codex CLI will automatically use .codex/config.toml if present
# Or copy to global config:
cp .codex/config.toml ~/.codex/config.toml

# Initialize or regenerate AGENTS.md with Codex:
codex
/init
```

**Documentation:**
- [Codex CLI Documentation](https://developers.openai.com/codex/cli/)
- [Configuring Codex](https://developers.openai.com/codex/local-config/)
- [Codex Security Guide](https://developers.openai.com/codex/security/)

### 2. Gemini CLI (Google)

**Configuration:** `.gemini/settings.json`

Gemini CLI can read `AGENTS.md` (or `GEMINI.md`) from the project root. The configuration file uses allowlists for tools and shell commands.

**Allowlisted commands:**
- `git`, `gh`, `uv`, `doit` - Development tools
- `python`, `pytest`, `ruff`, `mypy` - Python tools
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Core tools enabled:**
- `ShellTool` - Execute shell commands
- `ReadFileTool`, `WriteFileTool` - File operations
- `LSTool`, `GrepTool` - File exploration

**Setup:**
```bash
# Gemini CLI automatically uses .gemini/settings.json if present
# Or copy to global config:
cp .gemini/settings.json ~/.gemini/settings.json

# Use YOLO mode to skip all permission prompts (use with caution):
gemini --yolo
# Or toggle auto-approve with Ctrl+Y during a session
```

**Documentation:**
- [Gemini CLI Configuration](https://geminicli.com/docs/get-started/configuration/)
- [Provide Context with GEMINI.md Files](https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html)
- [Sandboxing in Gemini CLI](https://geminicli.com/docs/cli/sandbox/)
- [Gemini CLI Settings](https://geminicli.com/docs/cli/settings/)

### 3. Claude Code (Anthropic)

**Configuration:** `.claude/` directory

Claude Code uses a reference file (`.claude/claude.md`) that imports `AGENTS.md`.

**Whitelisted commands:**
- `git:*` - All git commands
- `gh:*` - All GitHub CLI commands
- `uv:*` - All uv commands
- `doit:*` - All doit commands
- File operations: `ls`, `cat`, `tree`, `find`, `grep`, `wc`, `mkdir`

**Setup:**
```bash
# Claude Code automatically detects .claude/ directory
# No additional setup needed
```

**Files:**
- `.claude/claude.md` - Imports AGENTS.md
- `.claude/settings.local.json` - Command permissions

### 4. Other AI Tools

The `AGENTS.md` file serves as general-purpose documentation for any AI coding assistant:

- **GitHub Copilot**: Reference in `.github/copilot-instructions.md`
- **Cursor**: Reference in `.cursorrules`
- **Codeium**: Reference in project settings
- **Tabnine**: Reference in configuration

## AGENTS.md - Universal Context File

The `AGENTS.md` file provides comprehensive project context including:

- Repository structure and architecture
- Development workflows and commands
- Code style and conventions
- Testing expectations
- CI/CD workflows
- Troubleshooting guides

This file is:
- **Read directly** by Codex CLI and Gemini CLI
- **Imported** by Claude Code via `.claude/claude.md`
- **Referenceable** by other AI tools

## Customization

### For Your Project

When using this template for a new project:

1. **Update AGENTS.md**: Customize project-specific details
2. **Adjust permissions**: Modify `.codex/config.toml` and `.claude/settings.local.json` as needed
3. **Add project commands**: Include any custom scripts or tools

### Adding New Commands

**Codex CLI** (`.codex/config.toml`):
```toml
[[approval_policy]]
type = "command"
pattern = "^your-command\\b"
action = "allow"
reason = "Description of command"
```

**Gemini CLI** (`.gemini/settings.json`):
```json
{
  "tools": {
    "allowed": [
      "run_shell_command(your-command)"
    ]
  }
}
```

**Claude Code** (`.claude/settings.local.json`):
```json
{
  "permissions": {
    "allow": [
      "Bash(your-command:*)"
    ]
  }
}
```

## Security Considerations

All configuration files are set up with security in mind:

**Whitelisted Operations:**
- Read-only file operations
- Safe git operations (status, diff, log, add, commit, push, pull)
- Package management (uv)
- Testing and linting (pytest, ruff, mypy)
- Task automation (doit)

**Protected Information:**
- API keys and tokens are excluded from environment variables
- No dangerous operations (rm -rf, format, etc.) are pre-approved
- Network operations require approval in some modes

## Troubleshooting

### Codex CLI

**Commands still prompt for approval:**
```bash
# Check current config
cat ~/.codex/config.toml

# Copy project config to global
cp .codex/config.toml ~/.codex/config.toml

# Or use project-specific config
codex --config .codex/config.toml
```

**Regenerate AGENTS.md:**
```bash
codex
/init
```

### Claude Code

**Permissions not working:**
- Ensure `.claude/settings.local.json` exists
- Check file is valid JSON
- Restart Claude Code

**Context not loading:**
- Verify `.claude/claude.md` contains `@AGENTS.md`
- Check `AGENTS.md` exists in project root

### Gemini CLI

**Commands still prompt for approval:**
```bash
# Check current config
cat ~/.gemini/settings.json

# Copy project config to global
cp .gemini/settings.json ~/.gemini/settings.json

# Or use YOLO mode (auto-approve all)
gemini --yolo

# Or toggle auto-approve during session
# Press Ctrl+Y
```

**Context not loading:**
- Ensure `AGENTS.md` or `GEMINI.md` exists in project root
- Check `.gemini/settings.json` has `"context": {"files": ["AGENTS.md"]}`
- Verify settings.json is valid JSON

## Resources

### Codex CLI
- [Codex CLI](https://developers.openai.com/codex/cli/)
- [Codex Configuration](https://developers.openai.com/codex/local-config/)
- [Codex Security Guide](https://developers.openai.com/codex/security/)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/)

### Gemini CLI
- [Gemini CLI Documentation](https://geminicli.com/docs/get-started/configuration/)
- [Gemini CLI Configuration](https://google-gemini.github.io/gemini-cli/docs/get-started/configuration.html)
- [GEMINI.md Context Files](https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html)
- [Sandboxing in Gemini CLI](https://geminicli.com/docs/cli/sandbox/)
- [Gemini CLI Settings](https://geminicli.com/docs/cli/settings/)
- [Gemini CLI GitHub](https://github.com/google-gemini/gemini-cli)

### Claude Code
- [Claude Code Documentation](https://claude.com/claude-code)
- [Claude Agent SDK](https://github.com/anthropics/claude-code)

### General AI Coding
- [GitHub Copilot](https://github.com/features/copilot)
- [Cursor](https://cursor.sh/)
- [Codeium](https://codeium.com/)

---

**Note**: The `.codex/`, `.gemini/`, and `.claude/` directories should be committed to version control to share consistent AI assistant configuration across the team.
