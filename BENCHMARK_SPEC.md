# CodeOwnership V0.1 Benchmark Specification

This is the pre-registration document. It is committed and hashed
(`python tools/co.py freeze`) before the implementation agent runs. After
that point, nothing in this repository except `runs/` may change.

## Purpose

CodeOwnership tests whether a developer can take responsibility for
AI-generated code after the coding agent is removed.

This pilot measures three separate things:

1. Perceived understanding
2. Debugging performance
3. Post-debugging comprehension

It does not produce a single ownership grade.

## Scope and honesty statement

This is a single-developer pilot. The author designed the benchmark and also
runs it, and knows the behavior of the mutation (but not where the mutation
lands in the agent's code). The pilot shows whether the instrument can be run
and whether it separates confidence, debugging and comprehension. It does not
show how developers in general behave. One run produces one anecdote.

## Task

Implement folder support for a note application. The application must support:

- creating notes
- creating folders
- assigning notes to folders
- removing notes from folders
- listing notes in a folder
- deleting folders
- retrieving notes

A note may belong to more than one folder.

## Public interface

The scaffold fixes these operations, exported from the `app` package. The
agent may choose everything behind them.

| Operation | Contract |
| --- | --- |
| `create_note(title, content)` | Returns a new note id. |
| `create_folder(name)` | Returns a new folder id. |
| `add_note_to_folder(note_id, folder_id)` | Returns `None`. |
| `remove_note_from_folder(note_id, folder_id)` | Returns `None`. |
| `list_folder_notes(folder_id)` | Returns a list of note dicts, ascending by id. |
| `delete_folder(folder_id)` | Returns `None`. |
| `get_note(note_id)` | Returns a dict or `None` if the note does not exist. |
| `reset()` | Clears all state and restarts id allocation (used by tests). |

Shared rules:

- Ids are positive integers, allocated in increasing order, never reused
  until `reset()`.
- A note dict has the keys `id`, `title`, `content`, `folder_ids` (a list).
- An unknown note or folder id raises `KeyError`, except `get_note`, which
  returns `None`.

Behaviors deliberately left unspecified (the agent decides, and the
comprehension questions ask about them afterwards):

- adding a note to a folder it is already in
- removing a note from a folder it is not in

## Hidden invariant

Never shown to the implementation agent.

- Deleting a folder removes that folder's memberships.
- It does not remove the notes themselves.
- A note with no remaining folder memberships continues to exist.
- A note with other folder memberships remains associated with those folders.
- Removing a membership with `remove_note_from_folder` never removes the note.

## Protocol

### Phase 1: Freeze

Commit and hash these before any agent runs:

`BENCHMARK_SPEC.md`, `AGENT_PROMPT.md`, `MUTATION_SPEC.md`, `INCIDENT.md`
(inside `views/debug/`), the scaffold (`app/`), all tests (`tests/`), the
rubric (`rubric/`), the tools (`tools/`), and the view templates (`views/`).

### Phase 2: Implementation agent

One run, one attempt, no retry. The agent works only in the **agent view**
(scaffold, visible tests, `AGENT_PROMPT.md`, neutral README). Record the model
name, model version, exact prompt, date and time, and the visible test result.

The hidden acceptance tests then run against the result.

- Pass: continue.
- Fail: record the failure and **end the pilot**.

### Phase 3: Confidence

After the hidden tests pass and before any mutation exists, record one rating:

> How confident are you that you understand this implementation well enough
> to modify it if something breaks?

Scale 1 to 5. Commit the answer.

### Phase 4: Mutation agent

One run, one attempt, no retry. A fresh session receives only the **mutation
view** (the agent's implementation, the visible tests, `MUTATION_SPEC.md`).
It receives neither the confidence rating nor any hint about the debugging
session.

Afterwards, run `python tools/co.py verify-mutation`. This verification was
written before the mutation agent ran. It exercises only public behavior: it
does not inspect files, function names, or Git state. It prints only a
verdict, and writes details to a sealed log that stays closed until the end of
Phase 6.

- Verified: continue.
- Not verified, or the mutation agent could not apply the change cleanly:
  record the failure and **end the pilot**.

The developer does not look at the mutation agent's diff, the repository
history for that step, or the sealed log before the debugging session ends.

### Phase 5: Debugging

The developer gets the **debug view**: the mutated `app/`, the visible tests,
a neutral README and `INCIDENT.md`. No hidden tests, specs, rubric, or history.
The coding agent is unavailable. External assistance is not used.

- Timer starts when `INCIDENT.md` is opened.
- Timer stops when the developer declares the defect fixed and verified.
- Cap: 60 minutes. Reaching the cap is recorded as `cap reached`. It is a
  result, not a failure of the benchmark.

### Phase 6: Explanation before scoring

Immediately after debugging, and before opening `rubric/SCORING.md`, the
developer writes and commits:

1. What caused the incident, and why did it affect one note but not the other?
2. What did you change to fix it?

Only after that commit, run `python tools/co.py check-fix` for the objective
result. Nothing the tool reports may influence the written explanation.

### Phase 7: Post-debugging comprehension

1. Inspect the original agent implementation and write an implementation
   specific answer key. Commit it.
2. Answer the four questions in `rubric/QUESTIONS.md`. Commit the answers.
3. Score against the key using `rubric/SCORING.md`.

The comprehension scores are explicitly post-debugging. They are not a second
blind measurement.

## Measurements

Perception:

- confidence from 1 to 5, recorded before the mutation exists

Debugging:

- fixed successfully (objective: `python tools/co.py check-fix`)
- total time to fix, or `cap reached`
- root cause identified (from the written explanation, scored after)
- regression test score, 0 to 3 (see `rubric/SCORING.md`)
- relevant tests passing (objective)
- files changed (objective)

Post-debugging comprehension:

- four rubric-scored questions, 0 to 4 each

No composite score is calculated.

## Reproducibility

Record in `runs/<run-id>/metadata.md`:

- model name and model version, for both agents
- exact prompts
- run date
- Python version and operating system
- benchmark commit and frozen hashes (`FROZEN_SHA256.txt`)
- agent implementation commit
- mutation description (the frozen behavioral spec, not a diff)
