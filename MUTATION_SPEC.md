Apply the behavioral change described below to the implementation in this repository.

Then verify that the changed behavior occurs and that unrelated behavior is unchanged. You may write temporary private tests to do this, but delete them before you finish.

Rules:

- Only modify files under `app/`. Do not add new files. Do not touch `tests/`.
- Do not add comments, docstrings, log messages, or names that describe or hint at the change.
- Keep the existing code style. The change should look like ordinary code.
- The provided visible test suite must still pass:

      python -m unittest discover -s tests/visible

- Do not use Git.

Behavior to introduce:

When a note loses its final folder membership as a consequence of deleting a folder, the note is incorrectly removed from the note store.

Removing a membership through `remove_note_from_folder` must not be changed by this mutation.

Notes with remaining folder memberships must not be removed by this mutation.
