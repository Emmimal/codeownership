from . import store


def create_note(title, content):
    return store.create_note(title, content)


def get_note(note_id):
    return store.get_note(note_id)
