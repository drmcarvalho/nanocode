#!/usr/bin/env python3
"""nanocode - minimal claude code alternative"""

import glob as globlib, json, os, re, shutil, subprocess, urllib.request, urllib.error
import sys
from typing import Any

"""OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/messages" if OPENROUTER_KEY else "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("MODEL", "anthropic/claude-opus-4.5" if OPENROUTER_KEY else "claude-opus-4-5")"""
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8080/v1/chat/completions")
MODEL = os.environ.get("MODEL", "qwen3.5-4b-mtp")

CTX_USED = 0   # tokens da ultima resposta (prompt + completion)
CTX_LIMIT = 0  # n_ctx do servidor, buscado na primeira chamada


# ANSI colors -- Windows consoles print the escapes literally unless VT mode is on
def enable_ansi():
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if os.name != "nt":
        return True
    import ctypes
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, mode.value | 0x4))  # VIRTUAL_TERMINAL


COLOR = enable_ansi()
RESET, BOLD, DIM = ("\033[0m", "\033[1m", "\033[2m") if COLOR else ("", "", "")
BLUE, CYAN, GREEN, YELLOW, RED = (
    (
        "\033[34m",
        "\033[36m",
        "\033[32m",
        "\033[33m",
        "\033[31m",
    )
    if COLOR
    else ("", "", "", "", "")
)


# Glyphs -- classic cmd.exe (conhost) fonts have no glyph for the fancy ones
def pick_glyphs():
    fancy = "❯", "⏺", "⎿", "│", "─"
    plain = ">", "*", "\\_", "|", "-"
    choice = os.environ.get("NANOCODE_GLYPHS", "auto")
    if choice == "ascii":
        return plain
    try:
        for glyph in fancy:
            glyph.encode(sys.stdout.encoding or "ascii")
    except (UnicodeEncodeError, LookupError):
        return plain  # redirecionado para cp1252/cp850: nem codifica
    if choice != "unicode" and os.name == "nt" and not os.environ.get("WT_SESSION"):
        return plain  # conhost codifica, mas a fonte nao tem o desenho
    return fancy


PROMPT, DOT, ELBOW, PIPE, LINE = pick_glyphs()


# --- Tool call implementations ---


def read(args):
    lines = open(args["path"], encoding='utf-8').readlines()
    offset = args.get("offset", 0)
    limit = args.get("limit", len(lines))
    selected = lines[offset : offset + limit]
    return "".join(f"{offset + idx + 1:4}| {line}" for idx, line in enumerate(selected))


def write(args):
    with open(args["path"], "w") as f:
        f.write(args["content"])
    return "ok"


def edit(args):
    text = open(args["path"], encoding='utf-8').read()
    old, new = args["old"], args["new"]
    if old not in text:
        return "error: old_string not found"
    count = text.count(old)
    if not args.get("all") and count > 1:
        return f"error: old_string appears {count} times, must be unique (use all=true)"
    replacement = (
        text.replace(old, new) if args.get("all") else text.replace(old, new, 1)
    )
    with open(args["path"], "w") as f:
        f.write(replacement)
    return "ok"


def glob(args):
    pattern = (args.get("path", ".") + "/" + args["pat"]).replace("//", "/")
    files: Any = globlib.glob(pattern, recursive=True)
    files = sorted(
        files,
        key=lambda f: os.path.getmtime(f) if os.path.isfile(f) else 0,
        reverse=True,
    )
    return "\n".join(files) or "none"


def grep(args):
    pattern = re.compile(args["pat"])
    hits = []
    for filepath in globlib.glob(args.get("path", ".") + "/**", recursive=True):
        try:
            for line_num, line in enumerate(open(filepath), 1):
                if pattern.search(line):
                    hits.append(f"{filepath}:{line_num}:{line.rstrip()}")
        except Exception as err:
            print(err, file=sys.stderr)
            return "none"
    return "\n".join(hits[:50]) or "none"


def bash(args):
    output_lines = []
    if ("cmd" in args and args["cmd"]
            and args["cmd"].strip().lower().removeprefix("sudo ").startswith((
        # Linux -- apagar arquivos
        "rm -rf", "rm -fr", "rm -r /", "rm -f /", "rm /", "rm *", "rm .",
        "find / ", "mv / ", "mv /home", "mv /etc",
        # Linux -- destruir discos
        "dd if=", "mkfs", "shred", "wipefs", "blkdiscard", "truncate",
        "fdisk", "sfdisk", "gdisk", "cfdisk", "parted", "umount",
        # Linux -- quebrar o sistema
        "chmod -r 777", "chmod 777 /", "chown -r", "chattr -i",
        "crontab -r", "userdel", "groupdel", "passwd root", "chroot",
        "iptables -f", "ip6tables -f", "systemctl stop", "systemctl disable",
        "apt-get purge", "apt purge", "apt-get remove", "yum remove",
        "dnf remove", "pacman -r", "pip uninstall",
        # Linux -- derrubar a maquina
        "shutdown", "reboot", "poweroff", "halt", "init 0", "init 6",
        "telinit", "kill -9 -1", "killall5", "pkill -9", ":(){",
        # Windows -- apagar arquivos
        "del /", "del *", "del c:", "erase", "deltree",
        "rd /s", "rmdir /s", "remove-item -recurse", "remove-item -force",
        # Windows -- destruir discos
        "format", "diskpart", "cipher /w", "fsutil",
        "format-volume", "clear-disk", "initialize-disk", "remove-partition",
        # Windows -- matar backup e boot (roteiro de ransomware)
        "vssadmin delete", "wbadmin delete", "wmic shadowcopy",
        "bcdedit", "bootrec", "bootsect", "wevtutil cl", "clear-eventlog",
        # Windows -- registro, contas e servicos
        "reg delete", "regedit", "net user", "net localgroup",
        "sc delete", "sc stop", "sc config", "taskkill /f",
        "takeown", "icacls c:", "cacls", "attrib -s -h",
        # Windows -- desligar as defesas e a maquina
        "set-mppreference", "netsh advfirewall set", "set-executionpolicy",
        "stop-computer", "restart-computer", "wmic os", "iex ", "invoke-expression",
    ))):
        output_lines.append(f"Forbidden to execute the {args['cmd']} command")
        return "".join(output_lines)
    proc = subprocess.Popen(
        args["cmd"], shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True
    )
    try:
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                print(f"  {DIM}{PIPE} {line.rstrip()}{RESET}", flush=True)
                output_lines.append(line)
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        output_lines.append("\n(timed out after 30s)")
    return "".join(output_lines).strip() or "(empty)"


# --- Tool definitions: (description, schema, function) ---

TOOLS = {
    "read": (
        "Read file with line numbers (file path, not directory)",
        {"path": "string", "offset": "number?", "limit": "number?"},
        read,
    ),
    "write": (
        "Write content to file",
        {"path": "string", "content": "string"},
        write,
    ),
    "edit": (
        "Replace old with new in file (old must be unique unless all=true)",
        {"path": "string", "old": "string", "new": "string", "all": "boolean?"},
        edit,
    ),
    "glob": (
        "Find files by pattern, sorted by mtime",
        {"pat": "string", "path": "string?"},
        glob,
    ),
    "grep": (
        "Search files for regex pattern",
        {"pat": "string", "path": "string?"},
        grep,
    ),
    "bash": (
        "Run shell command",
        {"cmd": "string"},
        bash,
    ),
}


def run_tool(name, args):
    try:
        return TOOLS[name][2](args)
    except Exception as err:
        return f"error: {err}"


def make_schema():
    result = []
    for name, (description, params, _fn) in TOOLS.items():
        properties = {}
        required = []
        for param_name, param_type in params.items():
            is_optional = param_type.endswith("?")
            base_type = param_type.rstrip("?")
            properties[param_name] = {
                "type": "integer" if base_type == "number" else base_type
            }
            if not is_optional:
                required.append(param_name)
        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return result


def fetch_ctx_limit():
    base = API_URL.split("/v1/")[0]
    props = json.loads(urllib.request.urlopen(base + "/props", timeout=5).read())
    return props["default_generation_settings"]["n_ctx"]


def call_api(messages, system_prompt):
    global CTX_USED, CTX_LIMIT
    if not CTX_LIMIT:
        CTX_LIMIT = fetch_ctx_limit()
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(
            {
                "model": MODEL,
                "max_tokens": 8192,
                "messages": [{"role": "system", "content": system_prompt}] + messages,
                "tools": make_schema(),
            }
        ).encode(),
        headers={
            "Content-Type": "application/json",
            # "anthropic-version": "2023-06-01",
            # **({"Authorization": f"Bearer {OPENROUTER_KEY}"} if OPENROUTER_KEY else {"x-api-key": os.environ.get("ANTHROPIC_API_KEY", "")}),
        },
    )
    try:
        response = urllib.request.urlopen(request)
        data = json.loads(response.read())
        CTX_USED = data["usage"]["total_tokens"]
        return data
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"llama-server HTTP {err.code}: {err.read().decode()[:500]}") from None
    except urllib.error.URLError as err:
        raise RuntimeError(f"llama-server unreachable at {API_URL}: {err.reason}") from None


def separator():
    width = min(shutil.get_terminal_size((80, 24)).columns, 80)
    pct = 100 * CTX_USED / (CTX_LIMIT or 1)
    color = GREEN if pct < 50 else YELLOW if pct < 80 else RED
    meter = f"ctx {pct:.0f}% ({CTX_USED}/{CTX_LIMIT})"
    return f"{DIM}{LINE * (width - len(meter) - 1)}{RESET} {color}{meter}{RESET}"


def render_markdown(text):
    return re.sub(r"\*\*(.+?)\*\*", f"{BOLD}\\1{RESET}", text)


def main():
    global CTX_USED
    # print(f"{BOLD}nanocode{RESET} | {DIM}{MODEL} ({'OpenRouter' if OPENROUTER_KEY else 'Anthropic'}) | {os.getcwd()}{RESET}\n")
    print(f"{BOLD}nanocode{RESET} | {DIM}{MODEL} (local llama) | {os.getcwd()}{RESET}\n")
    messages = []
    system_prompt = f"Concise coding assistant. cwd: {os.getcwd()}"
    while True:
        try:
            print(separator())
            user_input = input(f"{BOLD}{BLUE}{PROMPT}{RESET} ").strip()
            print(separator())
            if not user_input:
                continue
            if user_input in ("/q", "exit", "/quit"):
                break
            if user_input in ("/c", "/clear"):
                messages = []
                CTX_USED = 0
                print(f"{GREEN}{DOT} Cleared conversation{RESET}")
                continue
            messages.append({"role": "user", "content": user_input})

            # agentic loop: keep calling API until no more tool calls
            while True:
                response = call_api(messages, system_prompt)
                message = response["choices"][0]["message"]

                reasoning = message.get("reasoning_content")
                if reasoning:
                    print(f"\n{DIM}{DOT} {reasoning.strip()}{RESET}")

                if message.get("content"):
                    print(f"\n{CYAN}{DOT}{RESET} {render_markdown(message['content'])}")
                tool_calls = message.get("tool_calls") or []
                messages.append(message)
                if not tool_calls:
                    break
                for call in tool_calls:
                    tool_name = call["function"]["name"]
                    raw_args = call["function"].get("arguments") or "{}"
                    try:
                        tool_args: dict | Any = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError:
                        tool_args = {}
                    arg_preview = str(next(iter(tool_args.values()), ""))[:50]
                    print(
                        f"\n{GREEN}{DOT} {tool_name.capitalize()}{RESET}({DIM}{arg_preview}{RESET})"
                    )
                    result = run_tool(tool_name, tool_args)
                    result_lines = result.split("\n")
                    preview = result_lines[0][:60]
                    if len(result_lines) > 1:
                        preview += f" ... +{len(result_lines) - 1} lines"
                    elif len(result_lines[0]) > 60:
                        preview += "..."
                    print(f"  {DIM}{ELBOW}  {preview}{RESET}")
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": result,
                        }
                    )
            print()
        except (KeyboardInterrupt, EOFError):
            print('Exit...')
            break
        except Exception as err:
            print(f"{RED}{DOT} Error: {err}{RESET}")


if __name__ == "__main__":
    main()
