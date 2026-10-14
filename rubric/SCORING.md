# Scoring

Do not open this file until `runs/<run-id>/explanation.md` is committed.

## Order of operations

1. Debugging finished.
2. Write `explanation.md` (cause, and what you changed). Commit.
3. Open this file for the first time.
4. Inspect `agent_original/` and write `answer_key.md`. Commit.
5. Write `answers.md` (Q1 to Q4). Commit.
6. Score. Record the scores in `results.md`.

## Root cause identified (yes or no)

Judged from `explanation.md`, not from the patch. Yes requires all of:

- it names the condition (a note with no other folder membership left),
- it names the action (deleting a folder removes the note itself),
- it explains why the other note was unaffected.

## Regression test score (0 to 3)

- 0: no test added
- 1: a test was added but does not reproduce the failure
- 2: a test reproduces the failure but does not cover the distinction between
  a note with one membership and a note with several
- 3: the test captures both cases: the note whose last membership goes
  survives, and a note with several memberships survives with the remaining
  ones intact

## Comprehension questions (0 to 4 each)

Write the answer key before you answer. For each question, the key lists four
specific, checkable facts about the original agent implementation, for example
the function name, the data structure, or the observed behavior. Each fact the
answer gets right is one point. Equivalent correct wording earns credit.
Maximum 16.

No composite score. No grade labels. Report the sub-scores.

## Self-scoring caveat

The author scores their own answers. The sequence above (write, commit, then
score) is the control. It reduces rewriting answers to fit the rubric. It does
not remove self-assessment bias, and the article should say so.
