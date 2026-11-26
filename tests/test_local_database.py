import tempfile
import unittest
from pathlib import Path
from services.database import SQLiteClient


class LocalDatabaseTests(unittest.TestCase):
    def test_roundtrip_update_and_paging(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            client = SQLiteClient(path)
            for i in range(3):
                row = client.table("plays").insert({
                    "match_date": f"2026-11-0{i+1}", "is_starred": False,
                    "video_urls": [{"angle_name": "PGM", "video_url": "example"}],
                    "dvsport_metadata": {"override": True}, "weekly_summary_note": "preserve",
                }).execute().data[0]
            page = client.table("plays").select("*").order("match_date", desc=True).range(1, 1).execute().data
            self.assertEqual(page[0]["id"], 2)
            client.table("plays").update({"is_starred": True, "dvsport_metadata": {"override": False}}).eq("id", "2").execute()
            saved = SQLiteClient(path).table("plays").select("*").eq("id", 2).execute().data[0]
            self.assertIs(saved["is_starred"], True)
            self.assertEqual(saved["weekly_summary_note"], "preserve")
            self.assertEqual(saved["video_urls"][0]["angle_name"], "PGM")
            self.assertEqual(saved["dvsport_metadata"], {"override": False})
            with self.assertRaises(ValueError):
                client.table("plays").update({"is_starred": True}).execute()
            with self.assertRaises(LookupError):
                client.table("plays").update({"is_starred": True}).eq("id", 99).execute()

    def test_recipient_filter_and_projection(self):
        with tempfile.TemporaryDirectory() as folder:
            client = SQLiteClient(Path(folder) / "test.db")
            client.table("email_recipients").insert([{"id": "one", "name": "One", "active": True}, {"id": "two", "name": "Two", "active": False}]).execute()
            self.assertEqual(client.table("email_recipients").select("name").eq("active", True).order("name").execute().data, [{"name": "One"}])


if __name__ == "__main__":
    unittest.main()
