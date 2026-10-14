#!/usr/bin/env python3
"""Self-test for the CodeOwnership harness.

Builds reference implementations (correct, correctly mutated, over-mutated,
cascade-deleting) and checks that the visible tests, hidden tests, mutation
verification, view exporter, freeze and new-run tools all behave as designed.

    python tools/selftest.py

Uses temporary directories only. Writes nothing into this checkout.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
CO = ROOT / "tools" / "co.py"

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"\n      {detail}" if detail and not cond else ""))


def co(*args, root=None, cwd=None):
    script = (Path(root) / "tools" / "co.py") if root else CO
    env = dict(os.environ)
    env["CODEOWNERSHIP_SEALED_DIR"] = str(SEALED)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-B", str(script), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )
    return proc.returncode, proc.stdout + proc.stderr


def replace_once(text, old, new):
    assert text.count(old) == 1, f"patch anchor not found exactly once: {old[:40]!r}"
    return text.replace(old, new)


DELETE_FOLDER_OLD = """    for link in [l for l in _links if l[1] == folder_id]:
        _links.discard(link)
    del _folders[folder_id]
"""

PATCHES = {
    "correct": lambda s: s,
    # Pre-registered behavior: a note that loses its last membership because a
    # folder was deleted is removed. Everything else unchanged.
    "mutated": lambda s: replace_once(
        s,
        DELETE_FOLDER_OLD,
        """    affected = {l[0] for l in _links if l[1] == folder_id}
    for link in [l for l in _links if l[1] == folder_id]:
        _links.discard(link)
    del _folders[folder_id]
    for note_id in affected:
        if not any(l[0] == note_id for l in _links):
            del _notes[note_id]
""",
    ),
    # Too much: membership removal also removes the orphaned note.
    "over_mutated": lambda s: replace_once(
        PATCHES["mutated"](s),
        "    _links.discard((note_id, folder_id))\n",
        """    _links.discard((note_id, folder_id))
    if not any(l[0] == note_id for l in _links):
        del _notes[note_id]
""",
    ),
    # Wrong in a different way: deleting a folder deletes every note in it.
    "cascade": lambda s: replace_once(
        s,
        DELETE_FOLDER_OLD,
        """    for note_id in {l[0] for l in _links if l[1] == folder_id}:
        for link in [l for l in _links if l[0] == note_id]:
            _links.discard(link)
        del _notes[note_id]
    del _folders[folder_id]
""",
    ),
}


def build_impl(base, name, extra=None):
    """Create base/<name>/app with the scaffold __init__ and a reference store."""
    d = base / name
    (d / "app").mkdir(parents=True)
    shutil.copy(ROOT / "app" / "__init__.py", d / "app" / "__init__.py")
    ref = ROOT / "reference" / "correct"
    store = PATCHES[name.split("@")[0]]((ref / "store.py").read_text())
    (d / "app" / "store.py").write_text(store)
    for f in ("notes.py", "folders.py"):
        shutil.copy(ref / f, d / "app" / f)
    if extra:
        extra(d)
    return d


def tree_names(d):
    return sorted(p.relative_to(d).as_posix() for p in Path(d).rglob("*") if p.is_file())


def _build():
    for line in (ROOT / "tools" / "co.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("BUILD = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"


def main():
    global SEALED
    tmp = Path(tempfile.mkdtemp(prefix="co_selftest_"))
    SEALED = tmp / "sealed"
    try:
        run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} of {len(results)} checks passed (harness {_build()})")
    return 1 if failed else 0


def run(tmp):
    impls = tmp / "impls"
    correct = build_impl(impls, "correct")
    mutated = build_impl(impls, "mutated")
    over = build_impl(impls, "over_mutated")
    cascade = build_impl(impls, "cascade")

    # --- the scaffold itself is unimplemented
    rc, out = co("baseline", "--target", ROOT)
    check("unimplemented scaffold fails the visible tests", rc == 1, out)

    # --- baseline (visible + hidden)
    rc, out = co("baseline", "--target", correct)
    check("correct implementation passes visible and hidden tests", rc == 0, out)
    rc, out = co("baseline", "--target", mutated)
    check("mutated implementation fails the hidden tests", rc == 1 and "hidden" in out, out)
    rc, out = co("baseline", "--target", cascade)
    check("cascade implementation fails the hidden tests", rc == 1, out)

    # --- verify-mutation
    rc, out = co("verify-mutation", "--target", mutated)
    check("verify-mutation accepts the correct mutation", rc == 0 and "MUTATION VERIFIED" in out, out)
    leaked = [w for w in ("TestLastMembership", "get_note", "delete_folder", "survive", "store.py") if w in out]
    check("verify-mutation output reveals no behavior or location", not leaked, str(leaked))
    rc, out = co("verify-mutation", "--target", correct)
    check("verify-mutation rejects an unmutated implementation", rc == 1 and "NOT VERIFIED" in out, out)
    rc, out = co("verify-mutation", "--target", over)
    check("verify-mutation rejects an over-mutated implementation", rc == 1 and "NOT VERIFIED" in out, out)
    rc, out = co("verify-mutation", "--target", cascade)
    check("verify-mutation rejects a cascade-deleting implementation", rc == 1 and "NOT VERIFIED" in out, out)
    check("verify-mutation wrote sealed logs", len(list((tmp / "sealed").glob("verify_mutation_*.log"))) >= 4)

    # --- check-fix
    rc, out = co("check-fix", "--target", correct, "--mutated", mutated)
    check("check-fix reports a repaired implementation as FIXED", rc == 0 and "FIXED" in out and "NOT FIXED" not in out, out)
    check("check-fix lists the changed file", "store.py" in out, out)
    rc, out = co("check-fix", "--target", mutated, "--mutated", mutated)
    check(
        "check-fix reports the unrepaired implementation as NOT FIXED",
        rc == 1 and "NOT FIXED" in out and "still present: yes" in out,
        out,
    )

    # --- agent view
    agent = tmp / "views" / "agent"
    rc, out = co("views", "agent", "--out", agent)
    check("agent view exports", rc == 0, out)
    names = tree_names(agent)
    banned = ("hidden", "verify", "reference", "BENCHMARK_SPEC", "MUTATION_SPEC", "rubric", "tools", "templates", "INCIDENT")
    check("agent view contains no spec, hidden test or tooling", not [n for n in names if any(b in n for b in banned)], str(names))
    check("agent view has the prompt, readme, scaffold and visible tests",
          {"AGENT_PROMPT.md", "README.md", "app/__init__.py", "tests/visible/test_basic_behavior.py"} <= set(names), str(names))
    rc, out = co("views", "agent", "--out", ROOT / "runs" / "should_not_exist")
    check("views refuses to export inside the checkout", rc != 0 and not (ROOT / "runs" / "should_not_exist").exists(), out)
    rc, out = co("views", "agent", "--out", agent)
    check("views refuses a non-empty output directory", rc != 0, out)

    # --- mutation view
    mview = tmp / "views" / "mutation"
    rc, out = co("views", "mutation", "--impl", correct, "--out", mview)
    check("mutation view exports", rc == 0, out)
    names = tree_names(mview)
    check("mutation view has the mutation spec and no hidden tests or verification",
          "MUTATION_SPEC.md" in names and not [n for n in names if "hidden" in n or "verify" in n or "BENCHMARK" in n], str(names))
    proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/visible"],
                          cwd=mview, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    check("visible tests run from inside the mutation view", proc.returncode == 0, proc.stderr[-400:])

    def add_hint(d):
        p = d / "app" / "store.py"
        p.write_text(p.read_text() + "\n# mutation applied here\n")
    hinted = build_impl(impls, "correct@hint", extra=add_hint)
    rc, out = co("views", "mutation", "--impl", hinted, "--out", tmp / "views" / "mutation_hint")
    check("mutation view rejects an implementation with tamper words", rc != 0 and not (tmp / "views" / "mutation_hint").exists(), out)

    # --- debug view
    dview = tmp / "views" / "debug"
    rc, out = co("views", "debug", "--impl", mutated, "--original", correct, "--out", dview)
    check("debug view exports", rc == 0, out)
    names = tree_names(dview)
    check("debug view has the incident report, readme, app and visible tests",
          {"INCIDENT.md", "README.md", "app/store.py", "tests/visible/test_basic_behavior.py"} <= set(names), str(names))
    check("debug view has no specs, hidden tests, rubric or tooling",
          not [n for n in names if any(b in n for b in banned if b != "INCIDENT")], str(names))
    proc = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/visible"],
                          cwd=dview, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    check("visible tests pass in the debug view (the bug is invisible to them)", proc.returncode == 0, proc.stderr[-400:])

    def add_file(d):
        (d / "app" / "extra.py").write_text("x = 1\n")
    extra = build_impl(impls, "mutated@extra", extra=add_file)
    rc, out = co("views", "debug", "--impl", extra, "--original", correct, "--out", tmp / "views" / "debug_extra")
    check("debug view rejects a changed file set without naming files", rc != 0 and "extra.py" not in out, out)

    def add_comment(d):
        p = d / "app" / "store.py"
        p.write_text(p.read_text() + "\n# deliberate\n")
    commented = build_impl(impls, "mutated@comment", extra=add_comment)
    rc, out = co("views", "debug", "--impl", commented, "--original", correct, "--out", tmp / "views" / "debug_comment")
    check("debug view rejects a hinting comment without naming the file", rc != 0 and "store.py" not in out, out)
    check("debug view leak scan wrote a sealed log", bool(list((tmp / "sealed").glob("leakscan_*.log"))))

    # --- report, in a throwaway copy of the checkout
    rcopy = tmp / "report_checkout"
    shutil.copytree(ROOT, rcopy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    rc, out = co("new-run", "--id", "r1", root=rcopy)
    rc, out = co("report", "--run", "r1", root=rcopy)
    rep = (rcopy / "runs" / "r1" / "REPORT.md")
    body = rep.read_text() if rep.is_file() else ""
    check("report on a blank run is INCOMPLETE and lists what is missing",
          rc == 0 and "INCOMPLETE" in body and "NOT RECORDED" in body, out)
    check("report states the pilot limits and computes no composite score",
          "anecdote" in body and "No composite score" in body and "STRONG" not in body, body[:300])

    def edit(name, old, new):
        p = rcopy / "runs" / "r1" / name
        p.write_text(p.read_text().replace(old, new))

    edit("metadata.md", "- Hidden tests result (pass or fail; fail ends the pilot):",
         "- Hidden tests result (pass or fail; fail ends the pilot): pass")
    edit("metadata.md", "- verify-mutation verdict:", "- verify-mutation verdict: MUTATION VERIFIED, nothing odd")
    rc, out = co("report", "--run", "r1", "--stdout", root=rcopy)
    check("a verified verdict containing the word 'nothing' does not end the pilot",
          "PILOT ENDED" not in out and "Outcome" not in out, out[:400])

    edit("metadata.md", "MUTATION VERIFIED, nothing odd", "MUTATION NOT VERIFIED")
    rc, out = co("report", "--run", "r1", "--stdout", root=rcopy)
    check("an unverified mutation is reported as a pilot that ended at Phase 4",
          "PILOT ENDED" in out and "Phase 4" in out and "Not reached" in out, out[:600])

    edit("metadata.md", "MUTATION NOT VERIFIED", "MUTATION VERIFIED")
    edit("metadata.md", "ends the pilot): pass", "ends the pilot): fail")
    rc, out = co("report", "--run", "r1", "--stdout", root=rcopy)
    check("failed hidden tests are reported as a pilot that ended at Phase 2",
          "PILOT ENDED" in out and "Phase 2" in out and "Perception" not in out, out[:600])

    edit("metadata.md", "ends the pilot): fail", "ends the pilot): pass")
    edit("confidence.md", "Rating:", "Rating: 9")
    rc, out = co("report", "--run", "r1", "--stdout", root=rcopy)
    check("an out-of-range confidence rating is flagged INVALID", "INVALID" in out and "1 to 5" in out, out)

    edit("results.md", "## Notes and limitations for this run\n",
         "## Notes and limitations for this run\n\nRan on a laptop with no network, so the model ran offline.\n")
    rc, out = co("report", "--run", "r1", "--stdout", root=rcopy)
    check("free-text notes without a colon are kept", "no network" in out, out[-300:])

    check("report never reads or quotes the sealed logs",
          "sealed" not in body.lower() or "sealed log" not in body.lower(), body[:200])

    # --- freeze and new-run, in a throwaway copy of the checkout
    copy = tmp / "checkout"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "FROZEN_SHA256.txt"))
    rc, out = co("freeze", root=copy)
    check("freeze writes FROZEN_SHA256.txt", rc == 0 and (copy / "FROZEN_SHA256.txt").is_file(), out)
    rc, out = co("freeze", "--check", root=copy)
    check("freeze --check passes on an untouched checkout", rc == 0, out)
    for rel in ("README.md", "tests/hidden/test_folder_invariants.py", "tools/co.py"):
        f = copy / rel
        f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    rc, out = co("freeze", "--check", root=copy)
    check("freeze --check ignores CRLF line endings (Git on Windows)", rc == 0, out)
    (copy / "tests" / "hidden" / "test_folder_invariants.py").write_text("# edited\n")
    rc, out = co("freeze", "--check", root=copy)
    check("freeze --check detects an edited frozen file", rc == 1 and "CHANGED: tests/hidden/test_folder_invariants.py" in out, out)
    rc, out = co("new-run", "--id", "r1", root=copy)
    meta = (copy / "runs" / "r1" / "metadata.md").read_text() if rc == 0 else ""
    check("new-run creates the run folder from templates", rc == 0 and "{{" not in meta and "r1" in meta, out)
    rc, out = co("freeze", "--check", root=copy)
    check("files under runs/ do not affect the frozen check", rc == 1 and "runs/" not in out, out)

    pilot_checks(tmp)


# ---------------------------------------------------------------- pilot scenarios


def load_co(checkout):
    spec = importlib.util.spec_from_file_location(f"co_{checkout.name}", checkout / "tools" / "co.py")
    mod = importlib.util.module_from_spec(spec)
    old = os.environ.get("CODEOWNERSHIP_SEALED_DIR")
    os.environ["CODEOWNERSHIP_SEALED_DIR"] = str(SEALED)
    try:
        spec.loader.exec_module(mod)
    finally:
        if old is None:
            os.environ.pop("CODEOWNERSHIP_SEALED_DIR", None)
        else:
            os.environ["CODEOWNERSHIP_SEALED_DIR"] = old
    return mod


def pilot_env(tmp, name):
    copy = tmp / name
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
    rc, out = co("freeze", root=copy)  # a real run is frozen before any agent starts
    assert rc == 0, out
    return copy, load_co(copy), tmp / f"{name}_work"


def run_pilot(copy, mod, work, handlers, clock, work_arg=None):
    mod.now = lambda: clock[0]

    def scripted(key, prompt):
        h = handlers.get(key)
        if h is None:
            raise mod.Pause()
        return h() if callable(h) else h

    mod.ask = scripted
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            rc = mod.main(["pilot", "--run", "r1", "--work", str(work_arg or work)])
        except SystemExit as e:
            rc = e.code
    return rc, buf.getvalue()


def make_handlers(copy, work, clock, impl="correct", mutate="mutated", elapsed=1200, explain=True, write_key=True):
    ref = ROOT / "reference" / "correct"
    run = copy / "runs" / "r1"

    def agent_done():
        app = work / "agent_view" / "app"
        (app / "store.py").write_text(PATCHES[impl]((ref / "store.py").read_text()))
        for f in ("notes.py", "folders.py"):
            shutil.copy(ref / f, app / f)
        return "done"

    def mutation_done():
        s = work / "mutation_view" / "app" / "store.py"
        if mutate:
            s.write_text(PATCHES[mutate](s.read_text()))
        return "done"

    def timer_stop():
        shutil.copy(ref / "store.py", work / "debug_view" / "app" / "store.py")
        clock[0] += elapsed
        return "fixed"

    def explanation():
        if explain:
            (run / "explanation.md").write_text(
                "# Incident explanation\n\n## Cause\nDeleting a folder removed any note whose only membership was that folder. "
                "The shared note kept another membership, so it survived.\n\n## Change\nStopped deleting the note in delete_folder.\n"
            )
        return "committed"

    def key():
        if not write_key:
            return "committed"
        body = []
        for q in range(1, 5):
            body.append(f"## Q{q}")
            body += [f"{i}. fact {i} about question {q}" for i in range(1, 5)]
        (run / "answer_key.md").write_text("# Answer key\n\n" + "\n".join(body) + "\n")
        return "committed"

    def answers():
        (run / "answers.md").write_text("# Answers\n\n" + "\n\n".join(f"## Q{q}\nMembership lives in a set of pairs in store.py, created by add_note_to_folder." for q in range(1, 5)) + "\n")
        return "committed"

    return {
        "agent_done": agent_done, "agent_model": "model-impl", "agent_version": "v1", "agent_config": "default",
        "confidence": "4", "confidence_committed": "committed",
        "mutation_done": mutation_done, "mutation_model": "model-mut", "mutation_version": "v2", "mutation_clean": "yes",
        "timer_start": "start", "timer_stop": timer_stop,
        "explanation_committed": explanation, "key_committed": key, "answers_committed": answers,
        "root_cause": "yes", "regression": "3", "q1": "4", "q2": "3", "q3": "4", "q4": "2",
    }


def state_of(copy):
    p = copy / "runs" / "r1" / "pilot_state.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def report_of(copy):
    p = copy / "runs" / "r1" / "REPORT.md"
    return p.read_text() if p.is_file() else ""


def pilot_checks(tmp):
    # 1. happy path
    copy, mod, work = pilot_env(tmp, "pilot_ok")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
    body = report_of(copy)
    check("pilot runs the whole protocol and ends at done", rc == 0 and state_of(copy).get("stage") == "done", out[-600:])
    check("pilot report is COMPLETE with nothing missing", "Status: **COMPLETE**" in body and "NOT RECORDED" not in body, body[:500])
    check("pilot recorded the scores, models and timer",
          all(s in body for s in ("| Total time to fix, or cap reached | 20:00 |", "| Fixed successfully (check-fix) | yes |",
                                  "| Q4 (0 to 4) | 2 |", "model-impl", "model-mut",
                                  "Confidence (1 to 5), recorded before the mutation | 4 |")), body)
    check("pilot never wrote the sealed logs into the run folder or report",
          "verify_mutation_" not in body and not list((copy / "runs" / "r1").rglob("*.log")))
    log = (copy / "runs" / "r1" / "debugging_log.md").read_text()
    check("pilot logged the order of the explanation and check-fix", "Order of events" in log and "check-fix run at" in log, log[-300:])
    check("pilot exported all three clean views",
          (work / "agent_view").is_dir() and (work / "mutation_view").is_dir() and (work / "debug_view").is_dir())

    # 2. hitting the cap
    copy, mod, work = pilot_env(tmp, "pilot_cap")
    clock = [10_000.0]
    run_pilot(copy, mod, work, make_handlers(copy, work, clock, elapsed=3700), clock)
    check("pilot records a cap reached when declared fixed after 60 minutes",
          "cap reached (declared fixed after 61:40)" in report_of(copy), report_of(copy)[-800:])

    # 3. the implementation fails the hidden tests: the pilot ends, no retry
    copy, mod, work = pilot_env(tmp, "pilot_baseline_fail")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock, impl="cascade"), clock)
    body = report_of(copy)
    check("pilot ends at Phase 2 when the hidden tests fail", state_of(copy).get("stage") == "ended" and "Phase 2" in body and "PILOT ENDED" in body, out[-500:])
    check("pilot goes no further after a failed baseline", not (work / "mutation_view").exists() and not (work / "debug_view").exists())
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
    check("pilot refuses to restart an ended pilot", "already ended" in out and not (work / "mutation_view").exists(), out)

    # 4. mutation not verified
    copy, mod, work = pilot_env(tmp, "pilot_not_verified")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock, mutate="over_mutated"), clock)
    body = report_of(copy)
    check("pilot ends at Phase 4 when the mutation is not verified", state_of(copy).get("stage") == "ended" and "Phase 4" in body, out[-500:])
    check("pilot exports no debug view after an unverified mutation", not (work / "debug_view").exists())

    # 5. mutation agent reports it could not apply the change
    copy, mod, work = pilot_env(tmp, "pilot_not_clean")
    clock = [10_000.0]
    h = make_handlers(copy, work, clock)
    h["mutation_clean"] = "no"
    run_pilot(copy, mod, work, h, clock)
    check("pilot ends when the mutation agent could not apply the change",
          state_of(copy).get("stage") == "ended" and not (copy / "runs" / "r1" / "agent_mutated" / "app").exists())

    # 6. pause and resume
    copy, mod, work = pilot_env(tmp, "pilot_resume")
    clock = [10_000.0]
    h = make_handlers(copy, work, clock)
    paused = dict(h)
    paused["mutation_done"] = lambda: (_ for _ in ()).throw(mod.Pause())
    rc, out = run_pilot(copy, mod, work, paused, clock)
    check("pilot pauses mid-run and saves its place", rc == 0 and state_of(copy).get("stage") == "mutation_wait" and "Paused" in out, out[-300:])
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
    check("pilot resumes from the saved stage and completes", rc == 0 and state_of(copy).get("stage") == "done", out[-500:])

    # 7. an empty explanation does not pass the gate
    copy, mod, work = pilot_env(tmp, "pilot_empty_explanation")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock, explain=False), clock)
    check("pilot will not continue past an empty explanation", state_of(copy).get("stage") == "explanation" and "looks empty" in out, out[-400:])

    copy, mod, work = pilot_env(tmp, "pilot_empty_key")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock, write_key=False), clock)
    check("pilot will not continue past an empty answer key", state_of(copy).get("stage") == "scoring_key" and "16 filled-in facts" in out, out[-400:])

    # 7c. typing 'done' before the agent has changed anything must not burn the single attempt
    copy, mod, work = pilot_env(tmp, "pilot_early_done")
    clock = [10_000.0]
    h = make_handlers(copy, work, clock)
    early = dict(h)
    early["agent_done"] = "done"
    rc, out = run_pilot(copy, mod, work, early, clock)
    check("pilot does not end the pilot when 'done' is typed before the agent has changed anything",
          state_of(copy).get("stage") == "agent_wait" and "nothing has been implemented" in out and "ended" not in state_of(copy).get("stage", ""), out[-400:])
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
    check("pilot completes normally once the agent has really finished", state_of(copy).get("stage") == "done", out[-400:])
    early = make_handlers(copy, work, clock)
    copy, mod, work = pilot_env(tmp, "pilot_early_done_confirm")
    h = make_handlers(copy, work, clock)
    h["agent_done"] = "done"
    h["no_changes_confirm"] = "confirm"
    rc, out = run_pilot(copy, mod, work, h, clock)
    check("pilot records a failed attempt only after an explicit 'confirm'", state_of(copy).get("stage") == "ended", out[-300:])
    copy, mod, work = pilot_env(tmp, "pilot_early_mutation_done")
    clock = [10_000.0]
    h = make_handlers(copy, work, clock)
    h["mutation_done"] = "done"
    rc, out = run_pilot(copy, mod, work, h, clock)
    check("pilot does not end the pilot when the mutation agent has not changed anything yet",
          state_of(copy).get("stage") == "mutation_wait" and "mutation agent's app/" in out, out[-300:])

    # 7d. '~' in --work and --out is expanded (PowerShell and cmd pass it through literally)
    copy, mod, work = pilot_env(tmp, "pilot_tilde")
    home = tmp / "fake_home"
    home.mkdir()
    saved = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
    os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
    try:
        clock = [10_000.0]
        rc, out = run_pilot(copy, mod, work, {}, clock, work_arg="~/co_home_pilot")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                mod.main(["views", "agent", "--out", "~/co_home_view"])
            except SystemExit:
                pass
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("pilot expands ~ in --work instead of creating a folder inside the checkout",
          (home / "co_home_pilot" / "agent_view" / "AGENT_PROMPT.md").is_file() and not (copy / "~").exists(), out[-300:])
    check("views expands ~ in --out", (home / "co_home_view" / "AGENT_PROMPT.md").is_file() and not (copy / "~").exists(), buf.getvalue()[-300:])

    # 7e. a checkout inside another repository is flagged before anyone runs `git add -A`
    if shutil.which("git"):
        parent = tmp / "git_parent"
        inner = parent / "codeownership"
        shutil.copytree(ROOT, inner, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
        subprocess.run(["git", "-C", str(parent), "init", "-q"], capture_output=True)
        rc, out = co("freeze", root=inner)
        check("freeze warns when the checkout sits inside another git repository",
              "inside another git repository" in out and "git init" in out, out)
        subprocess.run(["git", "-C", str(inner), "init", "-q"], capture_output=True)
        rc, out = co("freeze", root=inner)
        check("freeze does not warn once the checkout has its own repository", "inside another" not in out, out)

    # 8. guards
    copy, mod, work = pilot_env(tmp, "pilot_frozen")
    (copy / "tests" / "hidden" / "test_folder_invariants.py").write_text("# edited\n")
    clock = [10_000.0]
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
    check("pilot refuses to start when a frozen file changed", rc not in (0, None) and not (copy / "runs" / "r1").exists(), out)
    copy, mod, work = pilot_env(tmp, "pilot_inside")
    rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, [0.0]), [0.0], work_arg=copy / "inside")
    check("pilot refuses a working directory inside the checkout", rc not in (0, None) and "OUTSIDE" in out, out)

    # 9. git enforcement
    if shutil.which("git"):
        copy, mod, work = pilot_env(tmp, "pilot_git")
        g = lambda *a: subprocess.run(["git", "-C", str(copy), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *a],
                                      capture_output=True, text=True)
        g("init", "-q")
        g("add", "-A")
        g("commit", "-q", "-m", "freeze")
        clock = [10_000.0]
        rc, out = run_pilot(copy, mod, work, make_handlers(copy, work, clock), clock)
        check("pilot pauses when the confidence rating is not committed",
              state_of(copy).get("stage") == "confidence_commit" and "not committed yet" in out, out[-400:])
        g("add", "-A")
        g("commit", "-q", "-m", "confidence")
        h = make_handlers(copy, work, clock)
        h["mutation_done"] = lambda: (_ for _ in ()).throw(mod.Pause())
        rc, out = run_pilot(copy, mod, work, h, clock)
        check("pilot continues once the confidence rating is committed",
              state_of(copy).get("stage") == "mutation_wait" and isinstance(state_of(copy).get("confidence_commit_time"), int), out[-400:])
    else:
        print("SKIP  git enforcement checks (git not installed)")


if __name__ == "__main__":
    sys.exit(main())
