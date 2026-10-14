"""Shared in-process storage for notes, folders, and their memberships."""

_notes = {}
_folders = {}
_next_id = 1


def allocate_id():
    """Return the next globally unique id for a note or folder."""
    global _next_id
    value = _next_id
    _next_id += 1
    return value


def reset():
    """Clear all notes, folders and memberships, and restart id allocation."""
    global _notes, _folders, _next_id
    _notes = {}
    _folders = {}
    _next_id = 1
