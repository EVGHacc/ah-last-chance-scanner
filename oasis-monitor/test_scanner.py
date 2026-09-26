import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('oasis_scanner', Path(__file__).with_name('scanner.py'))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)

class ParsingTests(unittest.TestCase):
    def test_dates(self):
        for date in s.DATES:
            day = date[-2:]
            for sample in (f'{day} juli 2027',f'2027-07-{day}',f'July {int(day)}, 2027',f'{day}/07/2027'):
                self.assertTrue(s.contains_date(sample,date),sample)
        self.assertFalse(s.contains_date('17 July 2027','2027-07-16'))
    def test_event_index_not_validated(self):
        both='Oasis Amsterdam 16 Jul 2027 17 Jul 2027 Johan Cruijff Arena'
        self.assertFalse(s.is_event(both,'https://www.ticketmaster.nl/artist/oasis-tickets/3668','2027-07-17'))
        self.assertFalse(s.is_event(both,'https://www.eventworld.com/oasis-amsterdam-tickets-16-07-2027/event/562155','2027-07-17'))
        self.assertTrue(s.is_event(both,'https://www.eventworld.com/oasis-amsterdam-tickets-16-07-2027/event/562155','2027-07-16'))
    def test_money(self):
        self.assertEqual(s.prices('from € 450,50 and €1.200,00'),[450.5,1200])
        self.assertEqual(s.money('5'),None)
        self.assertEqual(s.prices('£250'),[])
    def test_category_and_de_dup(self):
        date='2027-07-17';items=s.extract_cards([
            dict(text='Front Standing 2 tickets € 510.00 including fees',href='https://x/listing/1'),
            dict(text='Front Standing 2 tickets € 510.00 including fees',href='https://x/listing/1'),
            dict(text='Rear Standing 4 tickets € 440',href='https://x/listing/2')],date,'stubhub-nl','https://x/event','now')
        self.assertEqual(len(items),2)
        self.assertEqual(items[0]['category'],'front_standing')
        self.assertEqual(items[0]['ticketCount'],2)
        self.assertTrue(items[0]['allIn'])
        self.assertIsNone(items[1]['allIn'])
    def test_aggregator_separate(self):
        text='viagogo Best price from 379 € StubHub International 1,439 available from 432 € StubHub from 490 € Ticombo 651 available from 515 €'
        xs=s.extract_eventworld(text,'2027-07-17','https://eventworld.com/event','now')
        self.assertEqual(len(xs),4)
        self.assertTrue(all(x['evidenceType']=='aggregator_quote' and x['listingCount'] is None for x in xs))
    def test_ticketswap_zero(self):
        self.assertEqual(s.ticketswap_counts('0 Beschikbaar • 0 Verkocht • 764 Gezocht'),{'available':0,'soldPlatformCounter':0,'wanted':764})
    def test_discover_same_domain_and_date(self):
        links=[{'href':'https://www.ticketmaster.nl/event/oasis-17','context':'Oasis Live 27 Amsterdam 17 July 2027'},
               {'href':'https://bad.example/event/17','context':'Oasis Amsterdam 17 July 2027'},
               {'href':'https://www.ticketmaster.nl/event/hotel','context':'Oasis Amsterdam 17 July 2027 Ticket + Hotel'}]
        self.assertEqual(s.discover(links,'2027-07-17','www.ticketmaster.nl'),links[0]['href'])
    def test_snapshot_qa_and_no_false_full(self):
        reg={'sources':[{'id':x} for x in s.TARGETS]}
        checks=[dict(date=d,source=src,checkStatus='technical_failure',checkedAt='now',evidenceUrl='https://source.example',eventValidated=False,listingVerified=False,allInVerified=False) for d in s.DATES for src in s.TARGETS]
        snap={'checks':checks,'listings':[],'sourceCoverage':{d:dict(pageVerified=0,listingVerified=0,allInVerified=0,total=10) for d in s.DATES}}
        s.validate_snapshot(snap,reg)
        snap['sourceCoverage']['2027-07-17']['pageVerified']=10
        with self.assertRaises(AssertionError): s.validate_snapshot(snap,reg)
    def test_change_only_comparable_quotes(self):
        old={'status':'complete','listings':[{'date':'2027-07-17','source':'eventworld','partner':'viagogo','category':None,'evidenceType':'aggregator_quote','allIn':None,'askingPriceEur':400}]}
        new={'listings':[{'date':'2027-07-17','source':'eventworld','partner':'viagogo','category':None,'evidenceType':'aggregator_quote','allIn':None,'askingPriceEur':380}]}
        self.assertEqual(s.compare(old,new)[0]['percent'],-5)

if __name__ == '__main__': unittest.main()
