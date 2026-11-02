import os
import pathlib
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import platforms


class NowReporting(unittest.TestCase):
    def test_verdict_is_one_line_and_replay_does_not_add_a_comment(self):
        comments = []
        writes = []

        def github(path, method='GET', body=None):
            if method == 'GET':
                self.assertEqual(path, '/issues/11852/comments?per_page=100&page=1')
                return comments
            writes.append((path, method, body))
            comments.append({'id': 42, 'body': body['body']})
            return comments[-1]

        with patch.dict(os.environ, {'NOW_ISSUE': '11852'}), patch.object(platforms, 'github', side_effect=github):
            platforms.report('heroku r1: VERDICT UNKNOWN\nworker evidence held', key='heroku:r1')
            platforms.report('heroku r1: VERDICT UNKNOWN\nworker evidence held', key='heroku:r1')

        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0][:2], ('/issues/11852/comments', 'POST'))
        self.assertEqual(len(writes[0][2]['body'].splitlines()), 1)
        self.assertIn('VERDICT UNKNOWN worker evidence held', writes[0][2]['body'])


if __name__ == '__main__':
    unittest.main()
