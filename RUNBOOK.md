# Runbook

Follow the phases in order. Everything below assumes you are in the
CodeOwnership checkout and that `WORK` is a directory **outside** it, for
example `~/co-work/r1`. Agents and the debug session run in `WORK`, never
inside the checkout, so they cannot read the specs in a parent directory.

`co` below means `python tools/co.py`.

## Guided mode (recommended)

After Phase 0 below (freeze, commit, tag), one command walks you through the rest:

    python tools/co.py pilot --run r1 --work ~/co-work/r1

`--work` must be outside the checkout (on Windows, for example `C:\co-work\r1`). The command exports each view, runs
the baseline, the mutation check and the objective fix check, records the
results in `runs/r1/`, and finishes with `REPORT.md`. It pauses at the steps only
you can do (running the agents, debugging, writing and committing files) and
saves its place. Run the same command again to resume.

What it enforces for you:

- It refuses to start if a frozen file has changed.
- No retries. A failed baseline, an unverified mutation, a mutation agent that
  could not apply the change, or a refused debug view ends the pilot and is reported.
- It will not treat an early `done` as a failed attempt. If the agent's code is
  unchanged, it waits unless you type `confirm`.
- If the checkout is a git repository, it checks that `confidence.md`,
  `explanation.md`, `answer_key.md` and `answers.md` are committed before moving on,
  and logs the commit times so the order of events is on record.
- It rejects an empty explanation, answer key or answers file.
- It runs the objective fix check only after your explanation is committed.

The steps below are the same protocol, run by hand.

## Phase 0: Freeze

    python tools/selftest.py        # expect: 72 of 72 checks passed
    co freeze                       # writes FROZEN_SHA256.txt
    git init
    git rev-parse --show-toplevel   # must print THIS folder, not a parent folder
    git add -A
    git status --short              # must list only about 33 files, all CodeOwnership
    git commit -m "Freeze CodeOwnership V0.1 benchmark"
    git tag v0.1-frozen

Run `git init` every time, even if you re-extracted the files. If this folder sits inside another
project, skipping it makes `git add -A` stage that whole project. Stop at the `git status` line
if it lists anything else.

If git says it does not know who you are, set your own name and email first
(use your real values, not the examples), then run the commit and tag again:

    git config user.name "Your Name"
    git config user.email "your-real-address@example.com"

Line endings do not matter here: the frozen hashes ignore CRLF versus LF.
    co new-run --id r1              # creates runs/r1 from the templates

Before every later phase, run `co freeze --check`. It must report no changes.

## Phase 2: Implementation agent (one attempt, no retry)

    co views agent --out WORK/agent_view

Start the implementation agent with `WORK/agent_view` as its working
directory. Its prompt is the full contents of `AGENT_PROMPT.md`. Give it
nothing else.

When it finishes:

    cp -r WORK/agent_view/app runs/r1/agent_original/app
    find runs/r1/agent_original -name __pycache__ -prune -exec rm -rf {} +
    co baseline --target runs/r1/agent_original

- `BASELINE PASSED`: continue.
- `BASELINE FAILED`: fill in `runs/r1/metadata.md`, report the result, and end the pilot.

Fill in the implementation agent section of `runs/r1/metadata.md`.

## Phase 3: Confidence

Read the agent's implementation as long as you like. Then fill in
`runs/r1/confidence.md` with one rating from 1 to 5, and commit it:

    git add runs/r1 && git commit -m "Record run r1 implementation and confidence"

Nothing has been broken yet.

## Phase 4: Mutation agent (one attempt, no retry)

    co views mutation --impl runs/r1/agent_original --out WORK/mutation_view

Start a **fresh** session with `WORK/mutation_view` as its working directory.
Its prompt is the full contents of `MUTATION_SPEC.md`. Do not mention your
confidence rating or the debugging session.

When it finishes, do not read its changes:

    cp -r WORK/mutation_view/app runs/r1/agent_mutated/app
    find runs/r1/agent_mutated -name __pycache__ -prune -exec rm -rf {} +
    co verify-mutation --target runs/r1/agent_mutated

- `MUTATION VERIFIED`: continue.
- `MUTATION NOT VERIFIED`, or the agent could not apply the change: report it and end the pilot.

Commit with a neutral message. Do not run `git diff`, `git show`, or
`git log -p`, and do not open the sealed log in `runs/sealed/` yet.

    git add runs/r1 && git commit -m "Update run r1 implementation"

## Phase 5: Debugging

    co views debug --impl runs/r1/agent_mutated --original runs/r1/agent_original --out WORK/debug_view

If it refuses, it will not say why. That is deliberate. Treat it as a failed
mutation step and report it.

Open **only** `WORK/debug_view` in your editor. Do not open the checkout, the
specs, the sealed logs, or `runs/r1/agent_original`. The coding agent and
outside help are off limits.

- Timer starts when you open `INCIDENT.md`.
- Timer stops when you declare the defect fixed and verified.
- Cap: 60 minutes. Write `cap reached` if you hit it.

Keep notes in a scratch file outside the checkout. Afterwards copy them into
`runs/r1/debugging_log.md`.

## Phase 6: Explanation first, then the objective check

Write `runs/r1/explanation.md` (cause, and what you changed) and commit it
before you see any score, so the result cannot shape the explanation:

    git add runs/r1 && git commit -m "Record run r1 debugging and explanation"

Then run the objective check and record its output in `runs/r1/results.md`:

    co check-fix --target WORK/debug_view --mutated runs/r1/agent_mutated

Only now may you open the sealed logs and `rubric/SCORING.md`.

## Phase 7: Comprehension

1. Read `runs/r1/agent_original` and write `runs/r1/answer_key.md`. Commit.
2. Answer `rubric/QUESTIONS.md` in `runs/r1/answers.md`. Commit.
3. Score using `rubric/SCORING.md`. Fill in `runs/r1/results.md`. Commit.

## Final report

    co report --run r1

This writes `runs/r1/REPORT.md` from the files you recorded. It reads only the
run folder and the frozen hashes. It never opens the sealed logs, and it
computes no composite score. Missing fields show as `NOT RECORDED` and
out-of-range scores as `INVALID`, so a report with gaps says `INCOMPLETE`. If the
pilot ended early, it says which phase and why. Add `--stdout` to preview
without writing the file.

Commit `REPORT.md` with the rest of the run.

## Reporting

Report what happened, including a failed baseline, an unverified mutation, or
a reached cap. State plainly that this was one run by the author, and list the
model names, versions, prompts and the frozen tag. Do not combine the scores
into one grade.
