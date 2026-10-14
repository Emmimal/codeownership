#!/usr/bin/env python3
"""CodeOwnership command line tool.

    python tools/co.py freeze [--check]
    python tools/co.py new-run --id r1
    python tools/co.py views agent    --out DIR
    python tools/co.py baseline       --target DIR
    python tools/co.py views mutation --impl DIR --out DIR
    python tools/co.py verify-mutation --target DIR
    python tools/co.py views debug    --impl DIR --original DIR --out DIR
    python tools/co.py check-fix      --target DIR --mutated DIR
    python tools/co.py report         --run r1
    python tools/co.py pilot          --run r1 --work DIR

A "target" or "impl" directory is any directory that contains an `app/` package.
Views must be exported OUTSIDE this checkout so an agent cannot read the specs
in a parent directory.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True

BUILD = "0.1.5"
ROOT = Path(__file__).resolve().parent.parent
RUNNER = ROOT / "tools" / "_runner.py"
VISIBLE = ROOT / "tests" / "visible"
HIDDEN = ROOT / "tests" / "hidden"
VERIFY = ROOT / "tests" / "verify"
SEALED = Path(os.environ.get("CODEOWNERSHIP_SEALED_DIR", ROOT / "runs" / "sealed"))
FROZEN = ROOT / "FROZEN_SHA256.txt"

# Words that must never appear in benchmark-authored files shown to a participant.
BENCH_MARKERS = re.compile(
    r"invariant|hidden|mutat|inject|unfiled|last membership|final membership|"
    r"remaining membership|no remaining|orphan|cascade|benchmark|codeownership|pre-?regist",
    re.I,
)
# Tamper markers for agent-written code.
TAMPER_STRICT = re.compile(
    r"mutat|inject|benchmark|codeownership|pre-?regist|hidden test|sabotag", re.I
)
TAMPER_BROAD = re.compile(
    TAMPER_STRICT.pattern + r"|\bbug\b|deliberate|intentional|incorrect|regression|incident",
    re.I,
)

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def die(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- helpers


def sha256(path):
    """Hash a file with line endings normalized to LF.

    Git on Windows may check files out with CRLF. Hashing without the line
    ending keeps FROZEN_SHA256.txt valid on every platform, while any real
    content change still changes the hash.
    """
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def rel_files(base, skip_dirs=("__pycache__",)):
    base = Path(base)
    out = []
    for p in sorted(base.rglob("*")):
        if p.is_file() and not any(part in skip_dirs for part in p.parts) and p.suffix != ".pyc":
            out.append(p.relative_to(base).as_posix())
    return out


def require_app(path, what="directory"):
    p = Path(path).expanduser().resolve()
    if not (p / "app" / "__init__.py").is_file():
        die(f"{what} {p} does not contain app/__init__.py")
    return p


def prepare_out(path):
    out = Path(path).expanduser().resolve()
    if out == ROOT or ROOT in out.parents:
        die(
            "Refusing to export a view inside the CodeOwnership checkout.\n"
            "An agent could read the specs in a parent directory. Choose a path outside it."
        )
    if out.exists() and any(out.iterdir()):
        die(f"{out} already exists and is not empty")
    out.mkdir(parents=True, exist_ok=True)
    return out


def copy_tree(src, dst):
    shutil.copytree(src, dst, ignore=IGNORE, dirs_exist_ok=True)


def read_text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def run_suite(tests_dir, target):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(target)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            [sys.executable, "-B", str(RUNNER), str(tests_dir)],
            cwd=str(target),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"crashed": True, "run": 0, "failed": [], "details": {}, "stderr": "timeout"}
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    try:
        summary = json.loads(lines[-1])
    except (IndexError, ValueError):
        return {
            "crashed": True,
            "run": 0,
            "failed": [],
            "details": {},
            "stderr": proc.stderr[-2000:],
        }
    summary["crashed"] = False
    return summary


def passed(summary):
    return (not summary["crashed"]) and summary["run"] > 0 and not summary["failed"]


def describe(name, s):
    if s["crashed"]:
        return f"{name}: the test run crashed"
    return f"{name}: {s['run']} run, {len(s['failed'])} failed"


def write_sealed(prefix, text):
    SEALED.mkdir(parents=True, exist_ok=True)
    path = SEALED / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------- freeze


def frozen_paths():
    out = []
    for p in sorted(ROOT.rglob("*")):
        if not p.is_file():
            continue
        r = p.relative_to(ROOT)
        if r.parts[0] in (".git", "runs"):
            continue
        if "__pycache__" in r.parts or p.suffix == ".pyc" or p.name == ".DS_Store":
            continue
        if r.as_posix() == FROZEN.name:
            continue
        out.append(r.as_posix())
    return out


def cmd_freeze(args):
    current = {p: sha256(ROOT / p) for p in frozen_paths()}
    if not args.check:
        FROZEN.write_text(
            "".join(f"{h}  {p}\n" for p, h in sorted(current.items())), encoding="utf-8"
        )
        print(f"Wrote {FROZEN.name} with {len(current)} files. Commit it with the frozen artifacts.")
        note = nested_repo_note()
        if note:
            print("\n" + note)
        return 0
    if not FROZEN.is_file():
        die("No FROZEN_SHA256.txt. Run `freeze` first.")
    recorded = {}
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        h, _, p = line.partition("  ")
        recorded[p] = h
    changed = sorted(p for p in current if p in recorded and current[p] != recorded[p])
    added = sorted(p for p in current if p not in recorded)
    missing = sorted(p for p in recorded if p not in current)
    if not (changed or added or missing):
        print(f"Frozen files unchanged ({len(current)} files).")
        return 0
    for label, items in (("CHANGED", changed), ("ADDED", added), ("MISSING", missing)):
        for p in items:
            print(f"{label}: {p}")
    print("The frozen benchmark no longer matches FROZEN_SHA256.txt.")
    return 1


# ---------------------------------------------------------------- new-run


def cmd_new_run(args):
    dest = ROOT / "runs" / args.id
    if dest.exists():
        die(f"{dest} already exists")
    shutil.copytree(ROOT / "templates" / "run", dest)
    for sub in ("agent_original", "agent_mutated"):
        (dest / sub).mkdir()
        (dest / sub / ".gitkeep").write_text("")
    today = datetime.now().strftime("%Y-%m-%d")
    for p in dest.glob("*.md"):
        p.write_text(
            read_text(p).replace("{{RUN_ID}}", args.id).replace("{{DATE}}", today),
            encoding="utf-8",
        )
    print(f"Created {dest.relative_to(ROOT)}")
    return 0


# ---------------------------------------------------------------- views


def scan_authored(out, rel_paths):
    """Scan benchmark-authored files in a view. Returns a list of (path, marker)."""
    hits = []
    for rel in rel_paths:
        p = out / rel
        files = [p] if p.is_file() else [q for q in sorted(p.rglob("*")) if q.is_file()]
        for f in files:
            m = BENCH_MARKERS.search(read_text(f))
            if m:
                hits.append((f.relative_to(out).as_posix(), m.group(0)))
    return hits


def finish_authored_scan(out, rel_paths):
    hits = scan_authored(out, rel_paths)
    if hits:
        shutil.rmtree(out, ignore_errors=True)
        for rel, marker in hits:
            print(f"LEAK: {rel} contains {marker!r}", file=sys.stderr)
        die("View not created: benchmark-authored files contain flagged words.", 1)


def view_agent(args):
    out = prepare_out(args.out)
    copy_tree(ROOT / "app", out / "app")
    copy_tree(VISIBLE, out / "tests" / "visible")
    shutil.copy(ROOT / "AGENT_PROMPT.md", out / "AGENT_PROMPT.md")
    shutil.copy(ROOT / "views" / "common" / "README.md", out / "README.md")
    finish_authored_scan(out, rel_files(out))
    print(f"Agent view written to {out}")
    print("Contents: " + ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


def view_mutation(args):
    impl = require_app(args.impl, "--impl")
    out = prepare_out(args.out)
    copy_tree(impl / "app", out / "app")
    copy_tree(VISIBLE, out / "tests" / "visible")
    shutil.copy(ROOT / "MUTATION_SPEC.md", out / "MUTATION_SPEC.md")
    shutil.copy(ROOT / "views" / "common" / "README.md", out / "README.md")
    finish_authored_scan(out, ["README.md", "tests"])
    flagged = [
        p for p in rel_files(out / "app") if TAMPER_STRICT.search(read_text(out / "app" / p))
    ]
    if flagged:
        shutil.rmtree(out, ignore_errors=True)
        die("View not created: the implementation already contains flagged words in: " + ", ".join(flagged), 1)
    print(f"Mutation view written to {out}")
    print("Contents: " + ", ".join(sorted(p.name for p in out.iterdir())))
    return 0


def view_debug(args):
    impl = require_app(args.impl, "--impl")
    original = require_app(args.original, "--original")
    if rel_files(impl / "app") != rel_files(original / "app"):
        die("FAIL: the mutated app/ has a different file set from the original. Details withheld.", 1)
    flagged = 0
    log = []
    for p in rel_files(impl / "app"):
        new = len(TAMPER_BROAD.findall(read_text(impl / "app" / p)))
        old = len(TAMPER_BROAD.findall(read_text(original / "app" / p)))
        if new > old:
            flagged += new - old
            log.append(f"{p}: {old} -> {new}")
    if flagged:
        path = write_sealed("leakscan", "\n".join(log) + "\n")
        die(
            f"FAIL: leak scan flagged {flagged} new marker(s) in app/. Details are in a sealed log.\n"
            f"Do not open {path} until the debugging session is over.",
            1,
        )
    out = prepare_out(args.out)
    copy_tree(impl / "app", out / "app")
    copy_tree(VISIBLE, out / "tests" / "visible")
    shutil.copy(ROOT / "views" / "common" / "README.md", out / "README.md")
    shutil.copy(ROOT / "views" / "debug" / "INCIDENT.md", out / "INCIDENT.md")
    finish_authored_scan(out, ["README.md", "INCIDENT.md", "tests"])
    print(f"Debug view written to {out}")
    print("Open INCIDENT.md to start the timer. Do not open anything else from the CodeOwnership checkout.")
    return 0


def cmd_views(args):
    return {"agent": view_agent, "mutation": view_mutation, "debug": view_debug}[args.kind](args)


# ---------------------------------------------------------------- baseline


def cmd_baseline(args):
    target = require_app(args.target, "--target")
    visible = run_suite(VISIBLE, target)
    hidden = run_suite(HIDDEN, target)
    print(describe("visible tests", visible))
    print(describe("hidden acceptance tests", hidden))
    ok = passed(visible) and passed(hidden)
    if not ok:
        for name, s in (("visible", visible), ("hidden", hidden)):
            for t in s["failed"]:
                print(f"  failed ({name}): {t}")
            if s["crashed"]:
                print(f"  {name} stderr: {s.get('stderr', '')}")
        print("BASELINE FAILED. Record this and end the pilot (no retry).")
        return 1
    print("BASELINE PASSED. Record your confidence rating next, before any mutation exists.")
    return 0


# ---------------------------------------------------------------- verify-mutation


def cmd_verify_mutation(args):
    target = require_app(args.target, "--target")
    visible = run_suite(VISIBLE, target)
    hidden = run_suite(HIDDEN, target)
    check = run_suite(VERIFY, target)
    visible_ok = passed(visible)
    hidden_ok = (
        not hidden["crashed"]
        and bool(hidden["failed"])
        and all(".TestLastMembership." in t for t in hidden["failed"])
    )
    check_ok = passed(check)
    verified = visible_ok and hidden_ok and check_ok
    log = [
        f"visible suite passes: {visible_ok}  ({describe('visible', visible)})",
        f"hidden failures confined to TestLastMembership: {hidden_ok}  ({describe('hidden', hidden)})",
        f"public mutation check passes: {check_ok}  ({describe('check', check)})",
        "",
        "hidden failed tests:",
        *[f"  {t}" for t in hidden["failed"]],
        "mutation check failed tests:",
        *[f"  {t}" for t in check["failed"]],
    ]
    path = write_sealed("verify_mutation", "\n".join(log) + "\n")
    if verified:
        print("MUTATION VERIFIED")
    else:
        print("MUTATION NOT VERIFIED. Record this and end the pilot (no retry).")
    print(f"Details are in a sealed log: {path}")
    print("Do not open it until the debugging session and your written explanation are done.")
    return 0 if verified else 1


# ---------------------------------------------------------------- check-fix


def diff_dirs(new, old):
    new_files, old_files = set(rel_files(new)), set(rel_files(old))
    changed = [p for p in sorted(new_files & old_files) if sha256(new / p) != sha256(old / p)]
    return changed + [f"{p} (added)" for p in sorted(new_files - old_files)] + [
        f"{p} (removed)" for p in sorted(old_files - new_files)
    ]


def cmd_check_fix(args):
    target = require_app(args.target, "--target")
    mutated = require_app(args.mutated, "--mutated")
    visible = run_suite(VISIBLE, target)
    hidden = run_suite(HIDDEN, target)
    check = run_suite(VERIFY, target)
    mutation_present = passed(check)
    fixed = passed(visible) and passed(hidden) and not mutation_present
    app_changes = diff_dirs(target / "app", mutated / "app")
    tests_dir = target / "tests" / "visible"
    test_changes = diff_dirs(tests_dir, VISIBLE) if tests_dir.is_dir() else []
    print(describe("visible tests", visible))
    print(describe("hidden acceptance tests", hidden))
    print(f"mutated behavior still present: {'yes' if mutation_present else 'no'}")
    print(f"files changed under app/ (vs mutated): {len(app_changes)}")
    for p in app_changes:
        print(f"  {p}")
    print(f"test files added or changed (vs original visible tests): {len(test_changes)}")
    for p in test_changes:
        print(f"  {p}")
    print("FIXED" if fixed else "NOT FIXED")
    return 0 if fixed else 1


# ---------------------------------------------------------------- report

SECTION_RE = re.compile(r"^##\s+(.*)$")
FIELD_RE = re.compile(r"^\s*(?:-\s*)?([^:#\s][^:]*?):\s*(.*)$")


def parse_fields(path):
    """Return {section heading: {field: value}} from a run template file."""
    sections = {"": {}}
    if not Path(path).is_file():
        return sections
    cur = ""
    for line in read_text(path).splitlines():
        m = SECTION_RE.match(line)
        if m:
            cur = m.group(1).strip()
            sections.setdefault(cur, {})
            continue
        m = FIELD_RE.match(line)
        if m:
            sections.setdefault(cur, {}).setdefault(m.group(1).strip(), m.group(2).strip())
    return sections


def field(sections, section_prefix, key_prefix):
    for name, fields in sections.items():
        if name.startswith(section_prefix):
            for key, value in fields.items():
                if key.startswith(key_prefix):
                    return value
    return ""


def raw_section(path, heading_prefix):
    """Return the free text under the first `## <heading_prefix>...` heading."""
    if not Path(path).is_file():
        return ""
    out, inside = [], False
    for line in read_text(path).splitlines():
        m = SECTION_RE.match(line)
        if m:
            if inside:
                break
            inside = m.group(1).strip().startswith(heading_prefix)
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def frozen_hash(rel):
    if not FROZEN.is_file():
        return "not frozen"
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        h, _, p = line.partition("  ")
        if p == rel:
            return h
    return "not listed"


def in_range(lo, hi):
    def check(value):
        m = re.match(r"\d+", value)
        return bool(m) and lo <= int(m.group(0)) <= hi

    check.expected = f"{lo} to {hi}"
    return check


def cmd_report(args):
    run = ROOT / "runs" / args.run
    if not run.is_dir():
        die(f"{run} does not exist. Create it with `new-run`.")
    meta = parse_fields(run / "metadata.md")
    conf = parse_fields(run / "confidence.md")
    dbg = parse_fields(run / "debugging_log.md")
    res = parse_fields(run / "results.md")

    problems = {"missing": 0, "invalid": 0}

    def row(label, value, check=None):
        if not value:
            problems["missing"] += 1
            return f"| {label} | NOT RECORDED |"
        if check is not None and not check(value):
            problems["invalid"] += 1
            return f"| {label} | {value} (INVALID: expected {check.expected}) |"
        return f"| {label} | {value} |"

    def table(rows):
        return "\n".join(["| Item | Value |", "| --- | --- |", *rows])

    hidden = field(meta, "Implementation", "Hidden tests result")
    applied = field(meta, "Mutation", "Mutation applied cleanly")
    verdict = field(meta, "Mutation", "verify-mutation verdict")
    ended = None
    if hidden.lower().startswith("fail"):
        ended = ("Phase 2", "the implementation agent failed the hidden acceptance tests")
    elif re.match(r"no\b", applied.strip().lower()):
        ended = ("Phase 4", "the mutation agent could not apply the mutation cleanly")
    elif re.search(r"\bnot\b", verdict.lower()):
        ended = ("Phase 4", "the mutation was not verified")

    conf_value = field(conf, "", "Rating") or field(res, "Perception", "Confidence")
    parts = []

    run_rows = [
        row("Run date", field(meta, "", "Created")),
        row("Python version", field(meta, "Environment", "Python version")),
        row("Operating system", field(meta, "Environment", "Operating system")),
        row("CodeOwnership commit", field(meta, "Environment", "CodeOwnership commit")),
        row("Implementation agent model", field(meta, "Implementation", "Model name")),
        row("Implementation agent version", field(meta, "Implementation", "Model version")),
        row("Implementation agent configuration", field(meta, "Implementation", "Agent configuration")),
        row("Visible tests result", field(meta, "Implementation", "Visible tests result")),
        row("Hidden tests result", hidden),
    ]
    if ended is None or ended[0] != "Phase 2":
        run_rows += [
            row("Mutation agent model", field(meta, "Mutation", "Model name")),
            row("Mutation agent version", field(meta, "Mutation", "Model version")),
            row("Mutation applied cleanly", applied),
            row("verify-mutation verdict", verdict),
        ]
    run_rows += [
        f"| Frozen hash, BENCHMARK_SPEC.md | {frozen_hash('BENCHMARK_SPEC.md')} |",
        f"| Frozen hash, AGENT_PROMPT.md | {frozen_hash('AGENT_PROMPT.md')} |",
        f"| Frozen hash, MUTATION_SPEC.md | {frozen_hash('MUTATION_SPEC.md')} |",
    ]
    parts.append("## Run\n\n" + table(run_rows))

    if ended:
        parts.append(
            f"## Outcome\n\n**The pilot ended at {ended[0]}: {ended[1]}.** "
            "This is a reportable result under the no-retry rule, not a harness fault."
        )
    if ended is None or ended[0] != "Phase 2":
        parts.append("## Perception\n\n" + table([row("Confidence (1 to 5), recorded before the mutation", conf_value, in_range(1, 5))]))
    if ended is None:
        timer = field(dbg, "", "Total time") or field(res, "Debugging", "Total time")
        parts.append(
            "## Debugging\n\n"
            + table(
                [
                    row("Fixed successfully (check-fix)", field(res, "Debugging", "Fixed successfully")),
                    row("Total time to fix, or cap reached", timer),
                    row("Root cause identified (yes or no)", field(res, "Debugging", "Root cause identified")),
                    row("Regression test score (0 to 3)", field(res, "Debugging", "Regression test score"), in_range(0, 3)),
                    row("Relevant tests passing (check-fix)", field(res, "Debugging", "Relevant tests passing")),
                    row("Files changed (check-fix)", field(res, "Debugging", "Files changed")),
                ]
            )
            + "\n\nThe written explanation is in `explanation.md`. Its commit time, "
            "compared with the `check-fix` run, shows it was written first."
        )
        parts.append(
            "## Post-debugging comprehension\n\n"
            + table([row(f"Q{i} (0 to 4)", field(res, "Post-debugging", f"Q{i}"), in_range(0, 4)) for i in (1, 2, 3, 4)])
            + "\n\nThese are post-debugging scores, not a second blind measurement. "
            "No composite score is computed."
        )
    else:
        parts.append("## Debugging and comprehension\n\nNot reached.")

    notes = raw_section(run / "results.md", "Notes")
    status = (
        "PILOT ENDED"
        if ended
        else "COMPLETE"
        if not (problems["missing"] or problems["invalid"])
        else f"INCOMPLETE ({problems['missing']} not recorded, {problems['invalid']} invalid)"
    )
    header = (
        f"# CodeOwnership V0.1 report: {args.run}\n\n"
        f"Status: **{status}**\n\n"
        "Single-developer pilot. The author designed the benchmark and ran it, and "
        "knew the behavior of the mutation but not where it landed. One run is an "
        "anecdote. It shows whether the instrument can be run and separates "
        "confidence, debugging and comprehension. It does not show how developers "
        "in general behave. Self-scored rubric.\n"
    )
    text = header + "\n" + "\n\n".join(parts) + "\n"
    if notes:
        text += f"\n## Notes\n\n{notes}\n"
    if args.stdout:
        print(text)
    else:
        (run / "REPORT.md").write_text(text, encoding="utf-8")
        print(f"Wrote runs/{args.run}/REPORT.md  [{status}]")
    return 0


# ---------------------------------------------------------------- pilot


class Pause(Exception):
    """Stop now and resume later. Progress is saved after every stage."""


def now():
    return time.time()


def ask(key, prompt):
    """Prompt the user. `key` names the prompt so tests can script it."""
    try:
        return input(prompt + " ").strip()
    except (EOFError, KeyboardInterrupt):
        raise Pause()


def ask_int(key, prompt, lo, hi):
    while True:
        v = ask(key, prompt)
        if re.fullmatch(r"\d+", v) and lo <= int(v) <= hi:
            return int(v)
        print(f"Enter a whole number from {lo} to {hi}.")


def ask_choice(key, prompt, choices):
    while True:
        v = ask(key, prompt).lower()
        if v in choices:
            return v
        print("Type one of: " + ", ".join(choices))


def capture(fn, *a):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = fn(*a)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else 1
    return rc, buf.getvalue()


def set_field(path, key_prefix, value, section_prefix=None):
    """Fill `key_prefix...: value` in a run template file. Returns True if found."""
    path = Path(path)
    lines = read_text(path).splitlines()
    cur = ""
    for i, line in enumerate(lines):
        m = SECTION_RE.match(line)
        if m:
            cur = m.group(1).strip()
            continue
        if section_prefix is not None and not cur.startswith(section_prefix):
            continue
        m = re.match(r"^(\s*(?:-\s*)?)([^:#\s][^:]*?):\s*(.*)$", line)
        if m and m.group(2).strip().startswith(key_prefix):
            lines[i] = f"{m.group(1)}{m.group(2)}: {value}"
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    print(f"  (could not record '{key_prefix}' in {path.name}; fill it in by hand)")
    return False


def iso(epoch=None):
    return datetime.fromtimestamp(now() if epoch is None else epoch).strftime("%Y-%m-%d %H:%M:%S")


def git_toplevel():
    """Root of the git repository that contains this checkout, or None."""
    if not shutil.which("git"):
        return None
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    out = r.stdout.strip()
    return Path(out).resolve() if r.returncode == 0 and out else None


def nested_repo_note():
    """A warning if this folder has no repository of its own but sits inside another one."""
    top = git_toplevel()
    if top is None or top == ROOT:
        return None
    return (
        f"NOTE: this folder is inside another git repository ({top}).\n"
        f"Run `git init` in {ROOT} first. Without it, `git add -A` stages everything in {top}\n"
        f"(virtual environments and other projects included). Check with: git rev-parse --show-toplevel"
    )


def git_state(rel):
    """None if there is no git repo, False if `rel` is not committed, else its commit time."""
    if not (ROOT / ".git").exists() or not shutil.which("git"):
        return None

    def git(*a):
        return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True)

    if git("ls-files", "--error-unmatch", rel).returncode != 0:
        return False
    if git("status", "--porcelain", "--", rel).stdout.strip():
        return False
    out = git("log", "-1", "--format=%ct", "--", rel).stdout.strip()
    return int(out) if out.isdigit() else False


def require_committed(rel, what):
    gs = git_state(rel)
    if gs is None:
        print(f"  Warning: no git repository here, so I cannot verify that {what} is committed.")
        return None
    if gs is False:
        print(f"  {rel} is not committed yet. Commit it, then run the same pilot command again.")
        raise Pause()
    return gs


def same_tree(a, b):
    a, b = Path(a), Path(b)
    fa, fb = rel_files(a), rel_files(b)
    return fa == fb and all(sha256(a / f) == sha256(b / f) for f in fa)


def confirm_unchanged(key, what, reference):
    print(f"  {what} is identical to {reference}: nothing has been implemented or changed yet.")
    print("  Typing 'done' too early would record a failed attempt, and there is no retry.")
    if ask(key, "Type 'confirm' to record this as a failed attempt, or press Enter to wait:").lower() != "confirm":
        raise Pause()


def filled_text(path):
    """Text the user wrote under the `##` headings (the template preamble does not count)."""
    out, inside = [], False
    for line in read_text(path).splitlines():
        s = line.strip()
        if SECTION_RE.match(line):
            inside = True
            continue
        if not inside or not s or s.startswith("#") or s.lower().startswith("timestamp"):
            continue
        out.append(s)
    return "\n".join(out)


class Ctx:
    def __init__(self, run_id, work):
        self.id = run_id
        self.run = ROOT / "runs" / run_id
        self.work = work
        self.state_path = self.run / "pilot_state.json"
        self.st = {"stage": "agent_export"}
        if self.state_path.is_file():
            self.st = json.loads(self.state_path.read_text(encoding="utf-8"))

    def save(self, stage=None):
        if stage:
            self.st["stage"] = stage
        self.state_path.write_text(json.dumps(self.st, indent=2), encoding="utf-8")

    def f(self, name):
        return self.run / name

    def end(self, phase, why):
        self.st["ended"] = {"phase": phase, "why": why}
        self.save("ended")
        print(f"\nPILOT ENDED at {phase}: {why}.")
        print("This is a reportable result under the no-retry rule. Do not retry.")


def say_phase(title):
    print(f"\n=== {title} ===")


def st_agent_export(c):
    say_phase("Phase 2: implementation agent (one attempt, no retry)")
    rc, out = capture(view_agent, argparse.Namespace(out=str(c.work / "agent_view")))
    print(out.strip())
    if rc:
        die("Could not export the agent view.", 1)
    print(f"\nStart the implementation agent with {c.work / 'agent_view'} as its working directory.")
    print("Its prompt is the full contents of AGENT_PROMPT.md. Give it nothing else.")
    c.save("agent_wait")


def st_agent_wait(c):
    while ask("agent_done", "Type 'done' when the agent has finished:").lower() != "done":
        pass
    src = c.work / "agent_view" / "app"
    if not (src / "__init__.py").is_file() or same_tree(src, ROOT / "app"):
        confirm_unchanged("no_changes_confirm", "The agent's app/", "the scaffold")
    meta = c.f("metadata.md")
    for key, label, prompt in (
        ("agent_model", "Model name", "Implementation agent model name (Enter to skip):"),
        ("agent_version", "Model version", "Implementation agent model version (Enter to skip):"),
        ("agent_config", "Agent configuration", "Implementation agent configuration, e.g. tool and mode (Enter to skip):"),
    ):
        v = ask(key, prompt)
        if v:
            set_field(meta, label, v, "Implementation")
    set_field(meta, "Date and time", iso(), "Implementation")
    c.save("baseline")


def st_baseline(c):
    src = c.work / "agent_view" / "app"
    if not (src / "__init__.py").is_file():
        print(f"No app/ found in {c.work / 'agent_view'}. Finish the agent run, then run the pilot again.")
        raise Pause()
    dst = c.f("agent_original") / "app"
    shutil.rmtree(dst, ignore_errors=True)
    copy_tree(src, dst)
    target = c.f("agent_original")
    visible, hidden = run_suite(VISIBLE, target), run_suite(HIDDEN, target)
    print(describe("visible tests", visible))
    print(describe("hidden acceptance tests", hidden))
    meta = c.f("metadata.md")
    set_field(meta, "Python version", platform.python_version(), "Environment")
    set_field(meta, "Operating system", f"{platform.system()} {platform.release()}", "Environment")
    if (ROOT / ".git").exists() and shutil.which("git"):
        sha = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if sha:
            set_field(meta, "CodeOwnership commit", sha, "Environment")
    else:
        set_field(meta, "CodeOwnership commit", "no git repository", "Environment")
    set_field(meta, "FROZEN_SHA256", "yes", "Environment")
    set_field(meta, "Visible tests result", "pass" if passed(visible) else "fail", "Implementation")
    set_field(meta, "Hidden tests result", "pass" if passed(hidden) else "fail", "Implementation")
    if not (passed(visible) and passed(hidden)):
        c.end("Phase 2", "the implementation agent failed the visible or hidden tests")
        return
    print("BASELINE PASSED.")
    c.save("confidence")


def st_confidence(c):
    say_phase("Phase 3: confidence (nothing has been broken yet)")
    print(f"Read the implementation in {c.f('agent_original') / 'app'} as long as you like.")
    print("\nHow confident are you that you understand this implementation well enough")
    print("to modify it if something breaks?  1 = not confident ... 5 = extremely confident")
    n = ask_int("confidence", "Rating (1 to 5):", 1, 5)
    set_field(c.f("confidence.md"), "Rating", str(n))
    set_field(c.f("confidence.md"), "Timestamp", iso())
    set_field(c.f("results.md"), "Confidence", str(n), "Perception")
    c.save("confidence_commit")


def st_confidence_commit(c):
    rel = f"runs/{c.id}/confidence.md"
    print(f"\nCommit it now, before the mutation exists:  git add runs/{c.id} && git commit -m \"Record run {c.id} implementation and confidence\"")
    ask("confidence_committed", "Type 'committed' when done:")
    c.st["confidence_commit_time"] = require_committed(rel, "the confidence file")
    c.save("mutation_export")


def st_mutation_export(c):
    say_phase("Phase 4: mutation agent (one attempt, no retry)")
    rc, out = capture(view_mutation, argparse.Namespace(impl=str(c.f("agent_original")), out=str(c.work / "mutation_view")))
    print(out.strip())
    if rc:
        set_field(c.f("metadata.md"), "Mutation applied cleanly", "no", "Mutation")
        c.end("Phase 4", "the mutation view could not be exported")
        return
    print(f"\nStart a FRESH session with {c.work / 'mutation_view'} as its working directory.")
    print("Its prompt is the full contents of MUTATION_SPEC.md. Do not mention your confidence")
    print("rating or the debugging session. Do NOT read its changes or diff.")
    c.save("mutation_wait")


def st_mutation_wait(c):
    while ask("mutation_done", "Type 'done' when the mutation agent has finished:").lower() != "done":
        pass
    src = c.work / "mutation_view" / "app"
    if not (src / "__init__.py").is_file() or same_tree(src, c.f("agent_original") / "app"):
        confirm_unchanged("no_changes_confirm", "The mutation agent's app/", "the implementation you gave it")
    meta = c.f("metadata.md")
    for key, label, prompt in (
        ("mutation_model", "Model name", "Mutation agent model name (Enter to skip):"),
        ("mutation_version", "Model version", "Mutation agent model version (Enter to skip):"),
    ):
        v = ask(key, prompt)
        if v:
            set_field(meta, label, v, "Mutation")
    set_field(meta, "Date and time", iso(), "Mutation")
    clean = ask_choice("mutation_clean", "Did the mutation agent report that it applied the change cleanly? (yes/no):", ("yes", "no"))
    set_field(meta, "Mutation applied cleanly", clean, "Mutation")
    if clean == "no":
        c.end("Phase 4", "the mutation agent could not apply the mutation cleanly")
        return
    src = c.work / "mutation_view" / "app"
    if not (src / "__init__.py").is_file():
        print(f"No app/ found in {c.work / 'mutation_view'}. Finish the mutation run, then run the pilot again.")
        raise Pause()
    dst = c.f("agent_mutated") / "app"
    shutil.rmtree(dst, ignore_errors=True)
    copy_tree(src, dst)
    rc, out = capture(cmd_verify_mutation, argparse.Namespace(target=str(c.f("agent_mutated"))))
    print(out.strip())
    set_field(meta, "verify-mutation verdict", "MUTATION VERIFIED" if rc == 0 else "MUTATION NOT VERIFIED", "Mutation")
    if rc:
        c.end("Phase 4", "the mutation was not verified")
        return
    print(f"\nCommit with a NEUTRAL message and do not look at the change:")
    print(f"  git add runs/{c.id} && git commit -m \"Update run {c.id} implementation\"")
    print("Do not run git diff, git show or git log -p, and do not open the sealed log yet.")
    c.save("debug_export")


def st_debug_export(c):
    say_phase("Phase 5: debugging")
    rc, out = capture(
        view_debug,
        argparse.Namespace(impl=str(c.f("agent_mutated")), original=str(c.f("agent_original")), out=str(c.work / "debug_view")),
    )
    if rc:
        print("The debug view could not be exported. Details are deliberately withheld.")
        set_field(c.f("metadata.md"), "verify-mutation verdict", "MUTATION NOT VERIFIED (debug view refused)", "Mutation")
        c.end("Phase 4", "the debug-view export refused")
        return
    print(out.strip())
    print(f"\nOpen ONLY {c.work / 'debug_view'}. Do not open the checkout, the specs, the sealed logs,")
    print("or runs/*/agent_original. No coding agent and no outside help.")
    print("Cap: 60 minutes.")
    c.save("debug_timer")


def st_debug_timer(c):
    if "debug_start" not in c.st:
        ask("timer_start", "Type 'start' when you open INCIDENT.md (this starts the timer):")
        c.st["debug_start"] = now()
        set_field(c.f("debugging_log.md"), "Timer started", iso(c.st["debug_start"]))
        c.save()
    print(f"Timer running since {iso(c.st['debug_start'])}. It keeps running if you close this window.")
    ans = ask_choice("timer_stop", "Type 'fixed' when you declare the defect fixed and verified, or 'cap' if you hit 60 minutes:", ("fixed", "cap"))
    elapsed = int(now() - c.st["debug_start"])
    mm, ss = divmod(elapsed, 60)
    if ans == "cap":
        total = "60:00 cap reached"
    elif elapsed >= 3600:
        total = f"cap reached (declared fixed after {mm}:{ss:02d})"
    else:
        total = f"{mm}:{ss:02d}"
    set_field(c.f("debugging_log.md"), "Timer stopped", iso())
    set_field(c.f("debugging_log.md"), "Total time", total)
    set_field(c.f("results.md"), "Total time to fix", total, "Debugging")
    print(f"Recorded total time: {total} (self-timed)")
    c.save("explanation")


def st_explanation(c):
    say_phase("Phase 6: explanation first, then the objective check")
    print(f"Write runs/{c.id}/explanation.md: what caused the incident and why it affected one note")
    print(f"but not the other, and what you changed. Commit it BEFORE any score is shown:")
    print(f"  git add runs/{c.id} && git commit -m \"Record run {c.id} debugging and explanation\"")
    ask("explanation_committed", "Type 'committed' when done:")
    if len(filled_text(c.f("explanation.md"))) < 40:
        print("explanation.md looks empty. Fill it in and commit it, then run the pilot again.")
        raise Pause()
    c.st["explanation_commit_time"] = require_committed(f"runs/{c.id}/explanation.md", "the explanation file")
    c.save("check_fix")


def st_check_fix(c):
    rc, out = capture(cmd_check_fix, argparse.Namespace(target=str(c.work / "debug_view"), mutated=str(c.f("agent_mutated"))))
    print(out.strip())
    ran_at = now()
    v = re.search(r"visible tests: (\d+) run, (\d+) failed", out)
    h = re.search(r"hidden acceptance tests: (\d+) run, (\d+) failed", out)
    files = re.search(r"vs mutated\): (\d+)", out)
    tfiles = re.search(r"vs original visible tests\): (\d+)", out)
    res = c.f("results.md")
    set_field(res, "Fixed successfully", "yes" if rc == 0 else "no", "Debugging")
    if v and h:
        tests = f"visible {int(v.group(1)) - int(v.group(2))}/{v.group(1)}, hidden {int(h.group(1)) - int(h.group(2))}/{h.group(1)}"
        set_field(res, "Relevant tests passing", tests, "Debugging")
    if files:
        set_field(res, "Files changed", f"{files.group(1)} under app/" + (f", {tfiles.group(1)} test files" if tfiles else ""), "Debugging")
    log = c.f("debugging_log.md")
    with open(log, "a", encoding="utf-8") as fh:
        ec = c.st.get("explanation_commit_time")
        fh.write(f"\n## Order of events\n\n- Explanation committed at: {iso(ec) if ec else 'not verifiable (no git repository)'}\n- check-fix run at: {iso(ran_at)}\n")
    c.save("scoring_key")


def st_scoring_key(c):
    say_phase("Phase 7: post-debugging comprehension")
    print("Sealed logs may now be opened, and so may rubric/SCORING.md.")
    print(f"1. Read {c.f('agent_original') / 'app'} and write runs/{c.id}/answer_key.md (four specific facts per question).")
    print(f"   Commit it:  git add runs/{c.id} && git commit -m \"Record run {c.id} answer key\"")
    ask("key_committed", "Type 'committed' when done:")
    if len(re.findall(r"^\d\.[ \t]+\S", read_text(c.f("answer_key.md")), re.M)) < 16:
        print("answer_key.md needs 16 filled-in facts (four per question). Finish it, then run the pilot again.")
        raise Pause()
    c.st["key_commit_time"] = require_committed(f"runs/{c.id}/answer_key.md", "the answer key file")
    c.save("scoring_answers")


def st_scoring_answers(c):
    print(f"2. Answer the four questions in rubric/QUESTIONS.md in runs/{c.id}/answers.md.")
    print(f"   Commit it:  git add runs/{c.id} && git commit -m \"Record run {c.id} answers\"")
    ask("answers_committed", "Type 'committed' when done:")
    if len(filled_text(c.f("answers.md"))) < 80:
        print("answers.md looks incomplete. Finish it, then run the pilot again.")
        raise Pause()
    t = require_committed(f"runs/{c.id}/answers.md", "the answers file")
    k = c.st.get("key_commit_time")
    if t and k and t < k:
        print("  Warning: answers.md was committed before answer_key.md. Say so in the article.")
    c.save("scoring_scores")


def st_scoring_scores(c):
    print("3. Score your answers using rubric/SCORING.md. Be strict.")
    res = c.f("results.md")
    rc_yes = ask_choice("root_cause", "Root cause identified (yes/no):", ("yes", "no"))
    set_field(res, "Root cause identified", rc_yes, "Debugging")
    reg = ask_int("regression", "Regression test score (0 to 3):", 0, 3)
    set_field(res, "Regression test score", str(reg), "Debugging")
    for i in (1, 2, 3, 4):
        n = ask_int(f"q{i}", f"Q{i} score (0 to 4):", 0, 4)
        set_field(res, f"Q{i}", str(n), "Post-debugging")
    c.save("report")


def st_report(c):
    rc, out = capture(cmd_report, argparse.Namespace(run=c.id, stdout=False))
    print(out.strip())
    c.save("done")
    print(f"\nDone. Read runs/{c.id}/REPORT.md and commit it with the rest of the run.")


PILOT_STAGES = {
    "agent_export": st_agent_export,
    "agent_wait": st_agent_wait,
    "baseline": st_baseline,
    "confidence": st_confidence,
    "confidence_commit": st_confidence_commit,
    "mutation_export": st_mutation_export,
    "mutation_wait": st_mutation_wait,
    "debug_export": st_debug_export,
    "debug_timer": st_debug_timer,
    "explanation": st_explanation,
    "check_fix": st_check_fix,
    "scoring_key": st_scoring_key,
    "scoring_answers": st_scoring_answers,
    "scoring_scores": st_scoring_scores,
    "report": st_report,
}


def cmd_pilot(args):
    work = Path(args.work).expanduser().resolve()
    if work == ROOT or ROOT in work.parents:
        die("--work must be OUTSIDE the CodeOwnership checkout, so an agent cannot read the specs.")
    rc, out = capture(cmd_freeze, argparse.Namespace(check=True))
    if rc:
        print(out.strip())
        die("The frozen benchmark has changed. Restore it (or re-freeze before any agent has run).", 1)
    note = nested_repo_note()
    if note:
        print(note + "\n(Commit checks are skipped until this folder has its own repository.)\n")
    run = ROOT / "runs" / args.run
    if not run.exists():
        rc, out = capture(cmd_new_run, argparse.Namespace(id=args.run))
        print(out.strip())
    c = Ctx(args.run, work)
    if c.st["stage"] in ("done", "ended"):
        print(f"Run {args.run} is already {c.st['stage']}. Rebuilding the report.")
        capture(cmd_report, argparse.Namespace(run=args.run, stdout=False))
        print(f"See runs/{args.run}/REPORT.md")
        return 0
    try:
        while c.st["stage"] not in ("done", "ended"):
            PILOT_STAGES[c.st["stage"]](c)
    except Pause:
        c.save()
        print(f"\nPaused at stage '{c.st['stage']}'. Run the same command again to resume.")
        return 0
    if c.st["stage"] == "ended":
        capture(cmd_report, argparse.Namespace(run=args.run, stdout=False))
        print(f"Report written: runs/{args.run}/REPORT.md")
    return 0


# ---------------------------------------------------------------- main


def main(argv=None):
    ap = argparse.ArgumentParser(prog="co.py", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=f"CodeOwnership harness {BUILD}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("freeze", help="write or check FROZEN_SHA256.txt")
    p.add_argument("--check", action="store_true")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("new-run", help="create runs/<id> from the templates")
    p.add_argument("--id", required=True)
    p.set_defaults(fn=cmd_new_run)

    p = sub.add_parser("views", help="export a clean working view")
    p.add_argument("kind", choices=["agent", "mutation", "debug"])
    p.add_argument("--out", required=True)
    p.add_argument("--impl", help="directory containing the app/ to export (mutation, debug)")
    p.add_argument("--original", help="directory containing the original app/ (debug only)")
    p.set_defaults(fn=cmd_views)

    p = sub.add_parser("baseline", help="run visible and hidden tests on an implementation")
    p.add_argument("--target", required=True)
    p.set_defaults(fn=cmd_baseline)

    p = sub.add_parser("verify-mutation", help="check the pre-registered mutation; prints a verdict only")
    p.add_argument("--target", required=True)
    p.set_defaults(fn=cmd_verify_mutation)

    p = sub.add_parser("check-fix", help="score the debugging result objectively")
    p.add_argument("--target", required=True, help="directory with the developer's final app/")
    p.add_argument("--mutated", required=True, help="directory with the mutated app/ as handed over")
    p.set_defaults(fn=cmd_check_fix)

    p = sub.add_parser("report", help="assemble runs/<id>/REPORT.md from what you recorded")
    p.add_argument("--run", required=True)
    p.add_argument("--stdout", action="store_true", help="print instead of writing REPORT.md")
    p.set_defaults(fn=cmd_report)

    p = sub.add_parser("pilot", help="guided, resumable walk through the whole pilot")
    p.add_argument("--run", default="r1")
    p.add_argument("--work", required=True, help="working directory OUTSIDE this checkout")
    p.set_defaults(fn=cmd_pilot)

    args = ap.parse_args(argv)
    if args.cmd == "views" and args.kind in ("mutation", "debug") and not args.impl:
        die(f"views {args.kind} needs --impl")
    if args.cmd == "views" and args.kind == "debug" and not args.original:
        die("views debug needs --original")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
