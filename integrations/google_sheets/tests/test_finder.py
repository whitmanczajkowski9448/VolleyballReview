import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..')))
from dvsport_finder import group_full_games, import_play, match_id


class FakeTable:
    def __init__(self):
        self.upserted = None
        self.updated = None
        self.last_id = None

    def upsert(self, payload, on_conflict=None):
        self.upserted = dict(payload)
        assert on_conflict == 'dvsport_id'
        return self

    def update(self, patch):
        self.updated = dict(patch)
        return self

    def eq(self, field, value):
        self.last_id = (field, value)
        return self

    def execute(self):
        return SimpleNamespace(data=[{'id': 'new-play-001'}])


class FakeDB:
    def __init__(self):
        self.t = FakeTable()

    def table(self, name):
        assert name == 'plays'
        return self.t


class FinderTests(unittest.TestCase):
    def test_group_full_games(self):
        item = {
            'Id': 'HOME/VIDEOS/2026/MVC/GAMES/TEAM_A/match.dvplaylist',
            'Url': 'https://filmroom.dvsport360.com/g.dvplaylist',
            'Title': '08.30.26 - TEAM A VS TEAM B - 12-56-23',
            'Type': 0,
            'NumberOfPlays': 120
        }
        groups = group_full_games([item])
        self.assertEqual(len(groups), 1)
        group = next(iter(groups.values()))
        self.assertEqual(group['conference'], 'MVC')
        self.assertEqual(group['match_date'], '2026-08-30')
        self.assertEqual(group['match_name'], 'TEAM A VS TEAM B')

    @patch('dvsport_finder._find_existing', return_value=None)
    @patch('dvsport_finder._plays')
    @patch('dvsport_finder._match')
    def test_manual_import_is_ungraded(self, get_match, get_plays, _find):
        get_match.return_value = {
            'match_id': 'abc', 'conference': 'MVC',
            'match_date': '2026-08-30', 'match_name': 'TEAM A VS TEAM B'
        }
        get_plays.return_value = {
            '21': {'angles': [{'angle_name': 'PGM', 'video_url': 'https://example.com/p.mp4'}],
                   'metadata': {'fields': {'SET': 3, 'Home': 15, 'Away': 12}},
                   'source': 'https://example.com/full.dvplaylist'}
        }
        db = FakeDB()
        result = import_play(db, 'cookie', 'abc', 21)
        self.assertEqual(result['status'], 'imported')
        self.assertEqual(db.t.upserted['play_type'], 'Saved')
        self.assertEqual(db.t.upserted['dvsport_play_number'], 21)
        self.assertNotIn('referee_judgment', db.t.upserted)
        self.assertNotIn('crs_outcome', db.t.upserted)
        self.assertEqual(len(db.t.upserted['video_urls']), 1)

    @patch('dvsport_finder._find_existing')
    @patch('dvsport_finder._plays')
    @patch('dvsport_finder._match')
    def test_existing_challenge_is_not_reclassified(self, get_match, get_plays, get_existing):
        get_match.return_value = {'match_id': 'abc', 'conference': 'MVC',
                                  'match_date': '2026-08-30', 'match_name': 'MATCH'}
        get_plays.return_value = {
            '21': {'angles': [{'angle_name': 'PGM', 'video_url': 'https://example.com/p.mp4'}],
                   'metadata': {'fields': {}}, 'source': 'https://example.com/full.dvplaylist'}
        }
        get_existing.return_value = {
            'id': 'existing-1', 'play_type': 'Challenge', 'referee_judgment': 'Correct',
            'video_urls': [], 'dvsport_metadata': {}
        }
        db = FakeDB()
        result = import_play(db, 'cookie', 'abc', 21)
        self.assertEqual(result['status'], 'existing')
        self.assertEqual(result['play_type'], 'Challenge')
        self.assertIsNone(db.t.upserted)
        self.assertNotIn('referee_judgment', db.t.updated)


if __name__ == '__main__':
    unittest.main()
