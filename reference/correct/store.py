"""Reference implementation. Used only to self-test the harness.

Never exported into any view. Never shown to the implementation agent.
"""

_notes = {}
_folders = {}
_links = set()  # (note_id, folder_id)
_next_note_id = 1
_next_folder_id = 1


def reset():
    global _next_note_id, _next_folder_id
    _notes.clear()
    _folders.clear()
    _links.clear()
    _next_note_id = 1
    _next_folder_id = 1


def create_note(title, content):
    global _next_note_id
    note_id = _next_note_id
    _next_note_id += 1
    _notes[note_id] = {"title": title, "content": content}
    return note_id


def create_folder(name):
    global _next_folder_id
    folder_id = _next_folder_id
    _next_folder_id += 1
    _folders[folder_id] = {"name": name}
    return folder_id


def _view(note_id):
    note = _notes[note_id]
    return {
        "id": note_id,
        "title": note["title"],
        "content": note["content"],
        "folder_ids": sorted(f for (n, f) in _links if n == note_id),
    }


def get_note(note_id):
    if note_id not in _notes:
        return None
    return _view(note_id)


def _require(note_id, folder_id):
    if note_id not in _notes:
        raise KeyError(note_id)
    if folder_id not in _folders:
        raise KeyError(folder_id)


def add_note_to_folder(note_id, folder_id):
    _require(note_id, folder_id)
    _links.add((note_id, folder_id))


def remove_note_from_folder(note_id, folder_id):
    _require(note_id, folder_id)
    _links.discard((note_id, folder_id))


def list_folder_notes(folder_id):
    if folder_id not in _folders:
        raise KeyError(folder_id)
    return [_view(n) for n in sorted(n for (n, f) in _links if f == folder_id)]


def delete_folder(folder_id):
    if folder_id not in _folders:
        raise KeyError(folder_id)
    for link in [l for l in _links if l[1] == folder_id]:
        _links.discard(link)
    del _folders[folder_id]
