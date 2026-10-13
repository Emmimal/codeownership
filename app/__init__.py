"""Notes and folders. The public interface is re-exported from here."""

from .notes import create_note, get_note
from .folders import (
    create_folder,
    add_note_to_folder,
    remove_note_from_folder,
    list_folder_notes,
    delete_folder,
)
from .store import reset

__all__ = [
    "create_note",
    "get_note",
    "create_folder",
    "add_note_to_folder",
    "remove_note_from_folder",
    "list_folder_notes",
    "delete_folder",
    "reset",
]
