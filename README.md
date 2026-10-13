# CodeOwnership

**Measure whether AI-generated code is still understood by the developer who owns it.**

Passing tests tells you whether software works today. It does not tell you
whether the developer who owns the code can explain it and repair it when the
coding agent is gone. CodeOwnership is a small, reproducible protocol for
checking that. It uses the Python standard library only. It needs no API, no
paid plan and no model download.

> **Status: V0.1, a single-developer pilot.** The author designed the benchmark
> and also ran it. One run shows that the instrument can be run. It does not
> show how developers in general behave. The only run so far is incomplete (see
> [Pilot result](#pilot-result-run-r1)).

Article: *Do You Still Own the Code Your AI Wrote? I Built CodeOwnership to
Measure It* (link to be added when published).

"Ownership" here means practical ownership: you can explain the code and fix it
without the agent. It says nothing about copyright or licensing of generated code.

---

## What it measures

Three separate things. They are never combined into one score.

| # | Measurement | How |
| --- | --- | --- |
| 1 | Perceived understanding | One confidence rating (1 to 5), committed to git after the AI-written code is verified and before anything is broken. |
| 2 | Debugging performance | A second agent plants one pre-registered behavioral defect in the first agent's code. You get an incident report, no coding agent and a 60-minute cap. An objective check then runs the hidden tests on your code. |
| 3 | Post-debugging comprehension | Four rubric-scored questions about the implementation the agent wrote. |

## The task

Folder support for a small notes library. A note can belong to several
folders. The hidden invariant: **deleting a folder removes its memberships, not
the notes.** The implementation agent chooses everything behind a fixed public
interface.

## How a run works

```text
  1  Freeze the rules      hash 31 files, commit, tag v0.1-frozen
  2  Agent writes code     one attempt, no retries
  3  Baseline check        11 visible + 13 hidden tests must pass   <-- gate
  4  Confidence, 1 to 5    committed to git BEFORE the bug exists
  5  Second agent breaks   one pre-registered behavior,
     the code              fresh session, you never see the diff
  6  Verify the mutation   verdict only: VERIFIED / NOT VERIFIED
  7  Debug, no AI          INCIDENT.md, 60-minute cap
  8  Write explanation     committed BEFORE any score is shown
  9  Objective fix check   hidden tests run on your code
 10  Comprehension Q1-Q4   rubric is opened only now
```

## How it stays honest

- **Pre-registration.** The benchmark files are hashed in `FROZEN_SHA256.txt`
  and tagged `v0.1-frozen`. The pilot refuses to run if a frozen file changed.
- **The benchmark owns the tests.** Hidden acceptance tests confirm the agent's
  code is correct before anything is broken.
- **No retries.** A failed baseline or an unverified mutation ends the pilot
  and gets reported.
- **Blind mutation.** The change is a behavior written down before the run,
  applied by a second agent. The developer does not see the diff.
- **Verdict-only verification.** The mutation check prints VERIFIED or NOT
  VERIFIED. Details go to a sealed log in `runs/sealed/`.
- **Clean working view.** The debugging copy has no git history, specs, hidden
  tests or rubric.
- **Write before score.** Confidence and explanation are committed before
  anything is scored.
- **Self-tests.** `tools/selftest.py` runs 72 checks on the harness itself.

These controls reduce specific ways a self-run test can go wrong. They do not
remove bias.

---

## Quick start

Python 3.9 or later. Standard library only.

```bash
python tools/selftest.py        # 72 checks on the harness
python tools/co.py freeze       # pre-register the benchmark, then follow RUNBOOK Phase 0
python tools/co.py pilot --run r1 --work ~/co-work/r1   # guided, resumable walk-through
```

Check the build with `python tools/co.py --version` (expect `0.1.5` or later).
On Windows PowerShell, a path such as `C:\co-work\r1` also works for `--work`.

`pilot` is the single command to run. It does the automatic steps, tells you
what only you can do (run the agents, debug), saves its place in
`runs/<id>/pilot_state.json`, and writes `runs/<id>/REPORT.md` at the end.
`RUNBOOK.md` describes each phase if you would rather run the commands yourself.

### Commands

`python tools/co.py <command>`

| Command | Purpose |
| --- | --- |
| `freeze` | Write or check `FROZEN_SHA256.txt`. |
| `new-run` | Create `runs/<id>` from the templates. |
| `views` | Export a clean working view (no history, specs, hidden tests, rubric). |
| `baseline` | Run visible and hidden tests on an implementation. |
| `verify-mutation` | Check the pre-registered mutation. Prints a verdict only. |
| `check-fix` | Score the debugging result objectively. |
| `report` | Assemble `runs/<id>/REPORT.md` from what you recorded. |
| `pilot` | Guided, resumable walk through the whole pilot. |

Run `python tools/co.py <command> --help` for each command's options.

---

## Project structure

```text
codeownership/
├── README.md                  This file
├── RUNBOOK.md                 Phase-by-phase instructions (Phase 0 to final report)
├── BENCHMARK_SPEC.md          Pre-registration: task, interface, protocol, measurements, scope
├── AGENT_PROMPT.md            Exact prompt for the implementation agent
├── MUTATION_SPEC.md           Exact prompt and behavioral spec for the mutation agent
├── FROZEN_SHA256.txt          Hashes of the 31 frozen files
├── LICENSE
├── .gitattributes             LF line endings (keeps hashes stable on Windows)
├── .gitignore
│
├── app/                       The scaffold: stubs and the public interface
│   ├── __init__.py            Public exports
│   ├── notes.py               Note operations
│   ├── folders.py             Folder operations (the deleted-folder rule lives here)
│   └── store.py               In-memory store
│
├── tests/
│   ├── visible/
│   │   └── test_basic_behavior.py       11 tests the agent can run
│   ├── hidden/
│   │   └── test_folder_invariants.py    13 acceptance tests the agent never sees
│   └── verify/
│       └── mutation_check.py            Public-behavior check behind verify-mutation
│
├── rubric/
│   ├── QUESTIONS.md           The four comprehension questions
│   └── SCORING.md             Scoring rules, opened only after the explanation is committed
│
├── views/
│   ├── common/README.md       Neutral README placed in every working view
│   └── debug/INCIDENT.md      Incident report given to the debugger
│
├── templates/run/             Copied into runs/<id>/ by `new-run`
│   ├── metadata.md            Models, versions, environment
│   ├── confidence.md          Confidence rating, committed before the mutation
│   ├── debugging_log.md       Debugging record and timer
│   ├── explanation.md         Written explanation, committed before any score
│   ├── results.md             Recorded results
│   ├── answers.md             Comprehension answers
│   └── answer_key.md          Facts about the implementation, used to score answers
│
├── reference/correct/         Reference implementation, used only to self-test the harness
│   ├── notes.py
│   ├── folders.py
│   └── store.py
│
├── tools/
│   ├── co.py                  Command-line tool (all commands above)
│   ├── _runner.py             Test-running helper
│   └── selftest.py            72 checks on the harness
│
└── runs/
    ├── sealed/                Sealed mutation-verification logs
    └── r1/                    The pilot run reported below
        ├── metadata.md
        ├── confidence.md
        ├── debugging_log.md
        ├── explanation.md
        ├── results.md
        ├── pilot_state.json   Where the guided pilot stopped
        └── REPORT.md          Generated report (INCOMPLETE)
```

---

## Pilot result: run `r1`

One developer, one task. The full report is `runs/r1/REPORT.md`.

| Measurement | Result |
| --- | --- |
| Implementation agent | ChatGPT (Auto), free account, Temporary Chat |
| Baseline | 11 of 11 visible, 13 of 13 hidden tests passed |
| Mutation | Applied by a fresh Claude sub-session. Verdict: MUTATION VERIFIED |
| Perceived understanding | 4 out of 5, committed before the mutation |
| Debugging | Stopped at 8:12 of a 60-minute cap without finding the defect |
| Written explanation | Committed the next day. States that the defect was not found in the timed session and was found on a later, untimed attempt (self-reported, not verified) |
| Objective fix check | NOT FIXED: 11 of 11 visible, 10 of 13 hidden tests passed, no files changed under `app/` |
| Comprehension | Not run |
| Report status | INCOMPLETE (6 fields not recorded) |

What this shows and does not show:

- Confidence 4 out of 5 did not predict finding the defect in the 8 minutes tried.
- It does not show that the developer could not fix the code. The session was
  stopped at 8:12 of 60 minutes.
- The log says `fixed` because the V0.1 tool only accepts `fixed` or `cap`. That
  entry is not a verified fix. V0.2 should add a "gave up" outcome and show the
  objective check beside the developer's own answer.
- The later discovery is the author's own account. Nothing in the harness records it.

**Errata.** `runs/r1/REPORT.md` lists the run date as 2026-10-10. The run took
place on 2026-10-12. The committed files were not edited.

---

## Limitations

- One developer, one run, one task. An anecdote, not evidence.
- The author designed the benchmark and knows what the mutation does, though not
  where it lands in the code.
- Self-scored rubric. The commit order reduces rewriting answers to fit, but it
  does not remove bias.
- Agent output varies between runs. Record the model, version and prompt.
- **The hidden tests, the rubric, the reference implementation and the
  mutation spec are public in this repository.** Anyone who reads them before
  running the benchmark loses the blind test. A fair run needs the runner to
  avoid those folders until the relevant phase.
- Run `r1` was incomplete, and the tools were not the same at every stage. The
  implementation came from a chat assistant through a ZIP upload, not from an
  agent working inside the project folder.
- Claude, Anthropic's AI assistant, helped build the harness and applied the
  mutation. The author ran the experiment.

## Planned for V0.2

- A "gave up" outcome, with the objective check shown beside the developer's answer.
- Run the debugging session after a break, not after a day of setup.
- Use an agent that works inside the project folder and runs the tests itself.
- Runs by other developers.

## References

- Bainbridge, L. (1983). Ironies of automation. *Automatica*, 19(6), 775-779. https://doi.org/10.1016/0005-1098(83)90046-8
- Naur, P. (1985). Programming as theory building. *Microprocessing and Microprogramming*, 15(5), 253-261. https://doi.org/10.1016/0165-6074(85)90032-8
- DeMillo, R. A., Lipton, R. J., & Sayward, F. G. (1978). Hints on test data selection: Help for the practicing programmer. *Computer*, 11(4), 34-41. https://doi.org/10.1109/C-M.1978.218136
- Nosek, B. A., Ebersole, C. R., DeHaven, A. C., & Mellor, D. T. (2018). The preregistration revolution. *PNAS*, 115(11), 2600-2606. https://doi.org/10.1073/pnas.1708274114
- METR (2025, July 10). Measuring the impact of early-2025 AI on experienced open-source developer productivity. https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- METR (2026, February 24). We are changing our developer productivity experiment design. https://metr.org/blog/2026-02-24-uplift-update/
- Anthropic (2026, January 29). How AI assistance impacts the formation of coding skills. https://www.anthropic.com/research/AI-assistance-coding-skills
- Python Software Foundation. unittest: Unit testing framework. https://docs.python.org/3/library/unittest.html

## License

MIT. See `LICENSE`.

## Author

Emmimal P. Alexander ([@Emmimal](https://github.com/Emmimal))
