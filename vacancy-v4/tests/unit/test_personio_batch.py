import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.personio_batch import run_batch

class PersonioBatchTests(unittest.TestCase):
    def test_green_and_zero_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'cfg.json'
            p.write_text(json.dumps({'sources':[{'name':'Coinmerce','board_url':'https://coinmerce.jobs.personio.com','feed_url':'https://coinmerce.jobs.personio.com/xml'}]}))
            job={'job_id':'1','title':'Risk','short_summary':'Risk management','job_url':'https://coinmerce.jobs.personio.com/job/1','apply_url':'https://coinmerce.jobs.personio.com/job/1/apply'}
            with patch('app.personio_batch.load_sources',return_value=[SimpleNamespace(name='Coinmerce')]),patch('app.personio_batch.parse_inventory',return_value=[job]):
                b=run_batch(fetcher=lambda _: 'xml',config_path=p)
            self.assertEqual((b['verified_complete'],b['failed']),(1,0))
            with patch('app.personio_batch.load_sources',return_value=[SimpleNamespace(name='Coinmerce')]),patch('app.personio_batch.parse_inventory',side_effect=ValueError('zero')):
                b=run_batch(fetcher=lambda _: 'xml',config_path=p)
            self.assertEqual((b['verified_complete'],b['failed']),(0,1))
