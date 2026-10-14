# Incident explanation (Phase 6)

Write this right after debugging. Commit it before opening rubric/SCORING.md.

## What caused the incident, and why did it affect one note but not the other?

## What did you change to fix it?

Timestamp:

Explanation (written after the timed session ended)

I did not find the bug during my original 8-minute-and-12-second debugging session. I stopped that attempt and returned to the problem later. On the second attempt, I found the defect in about 30 minutes.

The bug was in delete_folder. The added code checked whether a note's folder_ids list had become empty after removing a folder membership. If the list was empty, it deleted the note from the store:

if not note["folder_ids"]:
    del store._notes[note_id]

This violates the intended behavior. Deleting a folder should remove the folder and its memberships, not delete the notes themselves. A note with other folder memberships would remain in the store, while a note that lost its last membership would be deleted.

I identified this behavior by investigating the mutated implementation. I did not complete the original debugging session successfully; I found the defect only after returning to the problem.

Finding the defect and verifying a fix are separate steps. The fix must be tested before I can claim that the problem has been resolved.
