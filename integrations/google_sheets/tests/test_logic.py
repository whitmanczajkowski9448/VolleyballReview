import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))
from logic import category, choose_category, compact_metadata, parse_angles, play_kind, sign_download, valid_download_token, zip_name


class LogicTests(unittest.TestCase):
    def test_play_type_normalization(self):
        self.assertEqual(play_kind('CHALLENGES'), 'Challenge')
        self.assertEqual(play_kind('Faults'), 'Fault')
        self.assertEqual(play_kind('Plays of Interest'), 'POI')

    def test_category_aliases(self):
        self.assertEqual(category('Ball Contact / Touch'), 'Touch')
        self.assertEqual(category('Back-row attack'), 'Attack Line')
        self.assertEqual(category('Service Foot Fault'), 'Service Line / CenterLine')
        self.assertEqual(category('Ball In / Out'), 'In/Out')
        self.assertEqual(category('Net fault / antenna'), 'Net')

    def test_review_fields_take_priority(self):
        self.assertEqual(choose_category({'crs_category':'Touch','challenge_type':'Net fault'}), 'Touch')

    def test_video_urls_jsonb_sort_and_dedup(self):
        angles = parse_angles('[{"angle_name":"ENDLINE","video_url":"https://media.test/e.mp4"},'
                              '{"angle_name":"PGM","video_url":"https://media.test/p.mp4"},'
                              '{"angle_name":"duplicate","video_url":"https://media.test/e.mp4"}]')
        self.assertEqual([a['name'] for a in angles], ['PGM','ENDLINE'])

    def test_legacy_dict_video_urls(self):
        self.assertEqual(parse_angles({'PGM':'https://media.test/p.mp4'})[0]['name'], 'PGM')

    def test_zip_name(self):
        play = {'id':'f-12', 'match_name':'Team A / Team B', 'match_date':'2026-11-11',
                'set_number':3,'crs_category':'Touch'}
        self.assertEqual(zip_name(play), '2026-11-11_Team A _ Team B_Set3_Touch_f-12.zip')

    def test_valid_signatures_expire(self):
        secret = 'secret-secret-secret-secret'
        expires = int(time.time()) + 30
        sig = sign_download('abc', expires, secret)
        self.assertTrue(valid_download_token('abc', expires, sig, secret))
        self.assertFalse(valid_download_token('def', expires, sig, secret))
        self.assertFalse(valid_download_token('abc', int(time.time()) - 1, sig, secret))

    def test_export_properties(self):
        p = {'id':'1','play_type':'Challenge','crs_category':'Touch','match_name':'Example',
             'referee_judgment':'Unclear','review_status':'Complete','video_urls':[]}
        v = compact_metadata(p, [], 'https://api.example.com', 'some-very-long-secret-value', 14, '')
        self.assertTrue(v['download_url'].startswith('https://api.example.com/api/v1/plays/1/download'))
        self.assertEqual(v['category'], 'Touch')
        self.assertEqual(v['referee_judgment'], 'Unclear')
        self.assertEqual(v['play_url'], '')


if __name__ == '__main__':
    unittest.main()
