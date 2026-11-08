import datetime as dt
import pathlib
import sys
import types
import unittest

ROOT=pathlib.Path(__file__).parent
sys.path.insert(0,str(ROOT))
import etf_tracker

class CatalogTests(unittest.TestCase):
    def test_catalog(self):
        rows,warnings=etf_tracker.read_catalog(ROOT/'etf_catalog.csv')
        self.assertFalse(warnings)
        self.assertEqual(len(rows),78)
        self.assertGreaterEqual(len(set(x['market'] for x in rows)),45)
        self.assertEqual(len(rows),len(set(x['symbol'] for x in rows)))
        records={x['symbol']:x for x in rows}
        self.assertEqual(records['CECL.L']['replication'],'Synthetic swap')
        self.assertEqual(records['SPOL.L']['replication'],'Physical full')
        self.assertEqual(records['FRIN.L']['market'],'India')
        self.assertEqual(records['HMCX.L']['market'],'UK FTSE 250')
        self.assertEqual(records['VAGP.L']['hedged'],'GBP')
        self.assertEqual(records['LTAM.L']['market'],'Latin America')
    def test_demo_does_not_invent_quotes(self):
        result=etf_tracker.demo(ROOT/'etf_catalog.csv')
        self.assertEqual(result['coverage']['quoted'],0)
        self.assertTrue(all(x['quote'] is None for x in result['funds']))
    def test_performance_uses_real_span(self):
        first=dt.date(2020,1,1)
        pts=[]
        for i in range(6*365):
            date=(first+dt.timedelta(days=i)).isoformat()
            price=100*1.05**(i/365.25)
            pts.append({'date':date,'close':price,'adjClose':price})
        compact=etf_tracker.compact_history(pts)
        self.assertGreater(len(compact),1800)
        for year in (1,3,5):
            ret,basis=etf_tracker.annualised_performance(compact,year)
            self.assertAlmostEqual(ret,5,delta=0.15)
            self.assertEqual(basis,'Adjusted close proxy')
    def test_missing_data_not_fabricated(self):
        record={'symbol':'FOO','quoteStatus':'Not downloaded','return1Y':None,'return3Y':None,'return5Y':None,'returnBasis':''}
        etf_tracker.attach(record,None,[])
        self.assertEqual(record['quoteStatus'],'Unavailable')
        self.assertIsNone(record['return1Y'])
    def test_collect_graceful_failures(self):
        class Core:
            @staticmethod
            def fetch_quote(info,opts):
                return (None,[],None,'not available')
        opts=types.SimpleNamespace(workers=3,years=5)
        payload,warnings,cached=etf_tracker.collect(Core(),opts,ROOT/'etf_catalog.csv',[],[],[],[])
        self.assertEqual(payload['coverage']['catalogued'],78)
        self.assertEqual(payload['coverage']['unavailable'],78)
        self.assertTrue(warnings)
        self.assertEqual(cached,0)

if __name__=='__main__':unittest.main()
