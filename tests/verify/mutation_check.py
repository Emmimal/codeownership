"""Independent mutation verification. Public behavior only.

Written before the mutation agent runs. It must not inspect files, function
names, Git state, or any implementation detail. It uses only the public
interface exported from `app`.

Passing means: the pre-registered mutation behavior is present, and the
neighboring behaviors the mutation spec says must not change are intact.
"""

import unittest

import app


def build():
    app.reset()
    work = app.create_folder("Work")
    python = app.create_folder("Python")
    a = app.create_note("A", "")
    b = app.create_note("B", "")
    c = app.create_note("C", "")
    app.add_note_to_folder(a, work)
    app.add_note_to_folder(a, python)
    app.add_note_to_folder(b, work)
    app.add_note_to_folder(c, python)
    return work, python, a, b, c


class MutationCheck(unittest.TestCase):
    def test_note_losing_final_membership_to_folder_delete_is_gone(self):
        work, python, a, b, c = build()
        app.delete_folder(work)
        self.assertIsNone(app.get_note(b))

    def test_note_with_remaining_membership_survives(self):
        work, python, a, b, c = build()
        app.delete_folder(work)
        note = app.get_note(a)
        self.assertIsNotNone(note)
        self.assertEqual(note["folder_ids"], [python])

    def test_unrelated_note_is_untouched(self):
        work, python, a, b, c = build()
        app.delete_folder(work)
        self.assertEqual(app.get_note(c)["folder_ids"], [python])
        self.assertEqual([n["id"] for n in app.list_folder_notes(python)], [a, c])

    def test_deleted_folder_is_gone(self):
        work, python, a, b, c = build()
        app.delete_folder(work)
        with self.assertRaises(KeyError):
            app.list_folder_notes(work)

    def test_membership_removal_does_not_remove_note(self):
        work, python, a, b, c = build()
        app.remove_note_from_folder(b, work)
        note = app.get_note(b)
        self.assertIsNotNone(note)
        self.assertEqual(note["folder_ids"], [])

    def test_membership_removal_of_one_of_several_keeps_note(self):
        work, python, a, b, c = build()
        app.remove_note_from_folder(a, work)
        self.assertEqual(app.get_note(a)["folder_ids"], [python])


if __name__ == "__main__":
    unittest.main()
