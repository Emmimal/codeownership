"""Note operations."""

from . import store


def create_note(title, content):
    """Create a note and return its id (a positive integer)."""
    note_id = store.allocate_id()
    store._notes[note_id] = {
        "id": note_id,
        "title": title,
        "content": content,
        "folder_ids": [],
    }
    return note_id


def get_note(note_id):
    """Return a copy of the note, or None when no such note exists."""
    note = store._notes.get(note_id)
    if note is None:
        return None
    return {
        "id": note["id"],
        "title": note["title"],
        "content": note["content"],
        "folder_ids": list(note["folder_ids"]),
    }
