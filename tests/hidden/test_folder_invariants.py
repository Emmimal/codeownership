"""Hidden acceptance tests. Never shown to the implementation agent.

They run once, after the agent finishes, to confirm the implementation honors
the invariant in BENCHMARK_SPEC.md. They are removed from every working view.

Test classes are grouped by which behavior they exercise. The mutation
verification (tools/co.py verify-mutation) relies on this grouping: after the
pre-registered mutation, only TestLastMembership may fail.
"""

import unittest

import app


def ids(notes):
    return [n["id"] for n in notes]


class Fixture(unittest.TestCase):
    """A -> Work + Python, B -> Work, C -> Python."""

    def setUp(self):
        app.reset()
        self.work = app.create_folder("Work")
        self.python = app.create_folder("Python")
        self.a = app.create_note("A", "shared")
        self.b = app.create_note("B", "work only")
        self.c = app.create_note("C", "python only")
        app.add_note_to_folder(self.a, self.work)
        app.add_note_to_folder(self.a, self.python)
        app.add_note_to_folder(self.b, self.work)
        app.add_note_to_folder(self.c, self.python)


class TestLastMembership(Fixture):
    """Deleting a folder must not remove a note whose only folder it was."""

    def test_note_with_only_that_folder_survives(self):
        app.delete_folder(self.work)
        self.assertIsNotNone(app.get_note(self.b))

    def test_surviving_note_is_unfiled_and_intact(self):
        app.delete_folder(self.work)
        note = app.get_note(self.b)
        self.assertEqual(note["folder_ids"], [])
        self.assertEqual(note["title"], "B")
        self.assertEqual(note["content"], "work only")

    def test_note_can_be_filed_again_afterwards(self):
        app.delete_folder(self.work)
        app.add_note_to_folder(self.b, self.python)
        self.assertEqual(ids(app.list_folder_notes(self.python)), [self.a, self.b, self.c])


class TestSharedNote(Fixture):
    """A note in several folders keeps its other folders."""

    def test_shared_note_survives_with_remaining_membership(self):
        app.delete_folder(self.work)
        note = app.get_note(self.a)
        self.assertIsNotNone(note)
        self.assertEqual(note["folder_ids"], [self.python])

    def test_other_folder_listing_is_intact(self):
        app.delete_folder(self.work)
        self.assertEqual(ids(app.list_folder_notes(self.python)), [self.a, self.c])

    def test_unrelated_note_is_untouched(self):
        app.delete_folder(self.work)
        note = app.get_note(self.c)
        self.assertEqual(note["folder_ids"], [self.python])
        self.assertEqual(note["content"], "python only")


class TestMembershipRemoval(Fixture):
    """Taking a note out of a folder never removes the note."""

    def test_removing_only_membership_keeps_note(self):
        app.remove_note_from_folder(self.b, self.work)
        note = app.get_note(self.b)
        self.assertIsNotNone(note)
        self.assertEqual(note["folder_ids"], [])
        self.assertEqual(ids(app.list_folder_notes(self.work)), [self.a])

    def test_removing_one_of_several_memberships_keeps_the_rest(self):
        app.remove_note_from_folder(self.a, self.work)
        note = app.get_note(self.a)
        self.assertEqual(note["folder_ids"], [self.python])

    def test_folder_still_exists_after_membership_removal(self):
        app.remove_note_from_folder(self.b, self.work)
        self.assertEqual(ids(app.list_folder_notes(self.work)), [self.a])


class TestFolderGone(Fixture):
    """The deleted folder is gone; the others are not."""

    def test_deleted_folder_no_longer_exists(self):
        app.delete_folder(self.work)
        with self.assertRaises(KeyError):
            app.list_folder_notes(self.work)
        with self.assertRaises(KeyError):
            app.add_note_to_folder(self.c, self.work)

    def test_other_folder_still_exists(self):
        app.delete_folder(self.work)
        self.assertEqual(len(app.list_folder_notes(self.python)), 2)

    def test_deleted_folder_not_in_any_folder_ids(self):
        app.delete_folder(self.work)
        for nid in (self.a, self.c):
            self.assertNotIn(self.work, app.get_note(nid)["folder_ids"])

    def test_empty_folder_can_be_deleted(self):
        empty = app.create_folder("Empty")
        app.delete_folder(empty)
        with self.assertRaises(KeyError):
            app.list_folder_notes(empty)


if __name__ == "__main__":
    unittest.main()
