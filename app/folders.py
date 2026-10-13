"""Folder operations."""


def create_folder(name):
    """Create a folder and return its id (a positive integer)."""
    raise NotImplementedError


def add_note_to_folder(note_id, folder_id):
    """Put a note in a folder. Returns None.

    Raises KeyError if the note or the folder does not exist.
    """
    raise NotImplementedError


def remove_note_from_folder(note_id, folder_id):
    """Take a note out of a folder. Returns None.

    Raises KeyError if the note or the folder does not exist.
    """
    raise NotImplementedError


def list_folder_notes(folder_id):
    """Return the notes in a folder as a list of note dicts, ascending by id.

    Each dict has the same shape as the one returned by get_note.
    Raises KeyError if the folder does not exist.
    """
    raise NotImplementedError


def delete_folder(folder_id):
    """Delete a folder. Returns None.

    Raises KeyError if the folder does not exist.
    """
    raise NotImplementedError
