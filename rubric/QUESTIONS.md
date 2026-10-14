# Post-debugging comprehension questions

Answer these after the debugging session, after you have written and committed
your incident explanation, and after you have written and committed the answer
key (`runs/<run-id>/answer_key.md`).

Answer from what you can explain about the **original agent implementation**.
You may look at the code while you answer. These are post-debugging scores, not
a blind recall test.

**Q1.** In this implementation, where is note-folder membership represented,
and which function is responsible for creating it?

**Q2.** What happens if `add_note_to_folder()` is called twice with the same
note and folder?

**Q3.** What does `remove_note_from_folder()` do when the requested membership
does not exist?

**Q4.** Which component or function is responsible for removing memberships
when a folder is deleted, and how does it interact with note storage?
