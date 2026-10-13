"""Note operations."""


def create_note(title, content):
    """Create a note and return its id (a positive integer)."""
    raise NotImplementedError


def get_note(note_id):
    """Return the note as a dict, or None if there is no such note.

    The dict has the keys "id", "title", "content" and "folder_ids".
    "folder_ids" is a list of the ids of the folders the note is in.
    """
    raise NotImplementedError
