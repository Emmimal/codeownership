import unittest

import app


def ids(notes):
    return [n["id"] for n in notes]


class BasicBehavior(unittest.TestCase):
    def setUp(self):
        app.reset()

    def test_create_note(self):
        nid = app.create_note("Title", "Body")
        note = app.get_note(nid)
        self.assertEqual(note["id"], nid)
        self.assertEqual(note["title"], "Title")
        self.assertEqual(note["content"], "Body")
        self.assertEqual(note["folder_ids"], [])

    def test_create_folder(self):
        fid = app.create_folder("Work")
        self.assertIsInstance(fid, int)
        self.assertEqual(app.list_folder_notes(fid), [])

    def test_ids_are_unique_and_increasing(self):
        a = app.create_note("A", "")
        b = app.create_note("B", "")
        self.assertGreater(b, a)
        f1 = app.create_folder("One")
        f2 = app.create_folder("Two")
        self.assertGreater(f2, f1)

    def test_add_note_to_folder(self):
        nid = app.create_note("A", "")
        fid = app.create_folder("Work")
        self.assertIsNone(app.add_note_to_folder(nid, fid))
        self.assertEqual(ids(app.list_folder_notes(fid)), [nid])
        self.assertEqual(app.get_note(nid)["folder_ids"], [fid])

    def test_remove_note_from_folder(self):
        nid = app.create_note("A", "")
        fid = app.create_folder("Work")
        app.add_note_to_folder(nid, fid)
        self.assertIsNone(app.remove_note_from_folder(nid, fid))
        self.assertEqual(app.list_folder_notes(fid), [])
        self.assertEqual(app.get_note(nid)["folder_ids"], [])

    def test_list_folder_notes(self):
        n1 = app.create_note("A", "")
        n2 = app.create_note("B", "")
        n3 = app.create_note("C", "")
        fid = app.create_folder("Work")
        app.add_note_to_folder(n3, fid)
        app.add_note_to_folder(n1, fid)
        listed = app.list_folder_notes(fid)
        self.assertEqual(ids(listed), [n1, n3])
        self.assertEqual(listed[0]["title"], "A")
        self.assertNotIn(n2, ids(listed))

    def test_get_note_unknown_returns_none(self):
        self.assertIsNone(app.get_note(9999))

    def test_note_can_appear_in_multiple_folder_lists(self):
        nid = app.create_note("A", "")
        f1 = app.create_folder("Work")
        f2 = app.create_folder("Python")
        app.add_note_to_folder(nid, f1)
        app.add_note_to_folder(nid, f2)
        self.assertEqual(ids(app.list_folder_notes(f1)), [nid])
        self.assertEqual(ids(app.list_folder_notes(f2)), [nid])
        self.assertEqual(set(app.get_note(nid)["folder_ids"]), {f1, f2})

    def test_delete_folder_removes_folder(self):
        fid = app.create_folder("Work")
        self.assertIsNone(app.delete_folder(fid))
        with self.assertRaises(KeyError):
            app.list_folder_notes(fid)

    def test_unknown_ids_raise_key_error(self):
        nid = app.create_note("A", "")
        fid = app.create_folder("Work")
        with self.assertRaises(KeyError):
            app.add_note_to_folder(9999, fid)
        with self.assertRaises(KeyError):
            app.add_note_to_folder(nid, 9999)
        with self.assertRaises(KeyError):
            app.remove_note_from_folder(9999, fid)
        with self.assertRaises(KeyError):
            app.remove_note_from_folder(nid, 9999)
        with self.assertRaises(KeyError):
            app.list_folder_notes(9999)
        with self.assertRaises(KeyError):
            app.delete_folder(9999)

    def test_reset_clears_everything(self):
        nid = app.create_note("A", "")
        fid = app.create_folder("Work")
        app.add_note_to_folder(nid, fid)
        app.reset()
        self.assertIsNone(app.get_note(nid))
        with self.assertRaises(KeyError):
            app.list_folder_notes(fid)
        self.assertIsInstance(app.create_note("B", ""), int)


if __name__ == "__main__":
    unittest.main()
