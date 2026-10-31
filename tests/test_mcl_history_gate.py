import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import build_mcl_history_fixture


class MclHistoryGateTests(unittest.TestCase):
    def test_partial_crosscheck_never_promotes_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            records=[{'date':f'2026-06-{i:02}'} for i in range(1,61)]
            (output/'collection.json').write_text(json.dumps({'failures':[],'records':records,'expected':[r['date'] for r in records]}))
            (output/'all-crosscheck.json').write_text(json.dumps([{'date':records[0]['date']}]))
            with patch.object(build_mcl_history_fixture,'OUT',output):
                with self.assertRaisesRegex(ValueError,'all 60'):
                    build_mcl_history_fixture.build()

    def test_new_history_also_requires_every_crosscheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)
            records=[{'date':f'day-{i:02}'} for i in range(40)]
            (output/'collection.json').write_text(json.dumps({'failures':[],'records':records,'expected':[r['date'] for r in records]}))
            (output/'crosscheck.json').write_text(json.dumps([{'date':records[0]['date']}]))
            with self.assertRaisesRegex(ValueError,'all 40'):
                build_mcl_history_fixture.build(output,40,'crosscheck.json')


if __name__=='__main__':unittest.main()
