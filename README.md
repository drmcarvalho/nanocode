# nanocode

Minimal Claude Code alternative. Single Python file, zero dependencies, for llamacpp local models.

Built using Claude Code, then used to build itself.

<img width="1282" height="618" alt="image" src="https://github.com/user-attachments/assets/a6b1f689-ceb3-4252-b7f6-57a504921fa6" />


## Features

- Full agentic loop with tool use
- Tools: `read`, `write`, `edit`, `glob`, `grep`, `bash`
- Conversation history
- Colored terminal output
- Context window info/usage

## Usage

```bash
python nanocode.py
```

To use a different model:

```bash
export MODEL="Qwen3.5-4B"
python nanocode.py
```

## Commands

- `/c` - Clear conversation
- `/q` or `exit` - Quit

## Tools

| Tool | Description |
|------|-------------|
| `read` | Read file with line numbers, offset/limit |
| `write` | Write content to file |
| `edit` | Replace string in file (must be unique) |
| `glob` | Find files by pattern, sorted by mtime |
| `grep` | Search files for regex |
| `bash` | Run shell command |

## Example

```
────────────────────────────────────────
❯ what files are here?
────────────────────────────────────────

⏺ Glob(**/*.py)
  ⎿  nanocode.py

⏺ There's one Python file: nanocode.py
```
