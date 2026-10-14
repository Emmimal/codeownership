"""Folder operations."""

from . import store


def create_folder(name):
    """Create a folder and return its id (a positive integer)."""
    folder_id = store.allocate_id()
    store._folders[folder_id] = {"id": folder_id, "name": name, "note_ids": set()}
    return folder_id


def add_note_to_folder(note_id, folder_id):
    """Add a note to a folder, raising KeyError for unknown ids."""
    if note_id not in store._notes:
        raise KeyError(note_id)
    if folder_id not in store._folders:
        raise KeyError(folder_id)

    # Sets make repeated additions harmless and preserve many-to-many membership.
    store._folders[folder_id]["note_ids"].add(note_id)
    folder_ids = store._notes[note_id]["folder_ids"]
    if folder_id not in folder_ids:
        folder_ids.append(folder_id)
        folder_ids.sort()
    return None


def remove_note_from_folder(note_id, folder_id):
    """Remove a membership, raising KeyError for unknown ids."""
    if note_id not in store._notes:
        raise KeyError(note_id)
    if folder_id not in store._folders:
        raise KeyError(folder_id)

    store._folders[folder_id]["note_ids"].discard(note_id)
    folder_ids = store._notes[note_id]["folder_ids"]
    if folder_id in folder_ids:
        folder_ids.remove(folder_id)
    return None


def list_folder_notes(folder_id):
    """Return copies of a folder's notes, ordered by ascending note id."""
    if folder_id not in store._folders:
        raise KeyError(folder_id)
    note_ids = sorted(store._folders[folder_id]["note_ids"])
    # Import locally to avoid coupling the module initialization order to notes.
    from .notes import get_note
    return [get_note(note_id) for note_id in note_ids]


def delete_folder(folder_id):
    """Delete a folder and remove its membership from every note."""
    if folder_id not in store._folders:
        raise KeyError(folder_id)
    folder = store._folders.pop(folder_id)
    for note_id in folder["note_ids"]:
        note = store._notes.get(note_id)
        if note is not None and folder_id in note["folder_ids"]:
            note["folder_ids"].remove(folder_id)
            if not note["folder_ids"]:
                del store._notes[note_id]
    return None
