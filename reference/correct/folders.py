from . import store


def create_folder(name):
    return store.create_folder(name)


def add_note_to_folder(note_id, folder_id):
    return store.add_note_to_folder(note_id, folder_id)


def remove_note_from_folder(note_id, folder_id):
    return store.remove_note_from_folder(note_id, folder_id)


def list_folder_notes(folder_id):
    return store.list_folder_notes(folder_id)


def delete_folder(folder_id):
    return store.delete_folder(folder_id)
