# Notes and folders

A small in-process library for notes and folders. A note can belong to more
than one folder.

## Public functions

All of these are exported from the `app` package.

| Function | Description |
| --- | --- |
| `create_note(title, content)` | Create a note and return its id. |
| `create_folder(name)` | Create a folder and return its id. |
| `add_note_to_folder(note_id, folder_id)` | Put a note in a folder. Returns `None`. |
| `remove_note_from_folder(note_id, folder_id)` | Take a note out of a folder. Returns `None`. |
| `list_folder_notes(folder_id)` | Return the notes in a folder as a list of note dicts, ascending by id. |
| `delete_folder(folder_id)` | Delete a folder. Returns `None`. |
| `get_note(note_id)` | Return the note dict, or `None` if there is no such note. |
| `reset()` | Clear all state and restart id allocation. The tests call this before each case. |

## Rules

- Ids are positive integers, allocated in increasing order, and never reused
  until `reset()` is called.
- A note dict has the keys `id`, `title`, `content` and `folder_ids` (a list
  of the ids of the folders the note is in).
- An unknown note or folder id raises `KeyError`. The one exception is
  `get_note`, which returns `None`.

## Running the tests

From the repository root:

    python -m unittest discover -s tests/visible

Python 3 with the standard library only. No packages to install.
