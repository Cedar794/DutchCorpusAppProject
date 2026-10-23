import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx

from lexicon_search.api_budget import BudgetUnavailable, OnlineModelBudget, money_units
from lexicon_search.query_rewrite import BailianQueryRewriter
from tests.test_query_rewrite import completion


class BudgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'budget.sqlite3'

    def budget(self,total='0.1',daily='0.1'):
        return OnlineModelBudget(str(self.path),total_cny=total,daily_cny=daily)

    async def test_zero_budget_blocks_before_transport_and_does_not_create_ledger(self):
        budget = self.budget(total='0')
        calls = []
        async with httpx.AsyncClient(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1/',
            transport=httpx.MockTransport(lambda r:calls.append(r)),
            event_hooks={'request':[budget.request],'response':[budget.response]}) as client:
            result = await BailianQueryRewriter(api_key='test',http_client=client).rewrite('original')
        self.assertEqual(result.status,'budget_unavailable')
        self.assertEqual(calls,[])
        self.assertFalse(self.path.exists())

    async def test_reservations_are_shared_across_instances_and_concurrency(self):
        budgets = [self.budget(total='0.0036864') for _ in range(6)]
        result = await asyncio.gather(*[
            asyncio.to_thread(b._reserve,'qwen3.7-flash',8192,256) for b in budgets],return_exceptions=True)
        self.assertEqual(sum(isinstance(r,str) for r in result),2)
        self.assertTrue(all(isinstance(r,(str,BudgetUnavailable)) for r in result))
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('select units from budget_totals where scope=\'all\'').fetchone()[0],36864)

    async def test_restart_keeps_pending_reservation_and_usage_releases_difference(self):
        budget = self.budget(total='0.002')
        identifier = budget._reserve('qwen3.7-flash',8192,256)
        restarted = self.budget(total='0.002')
        with self.assertRaises(BudgetUnavailable):
            restarted._reserve('qwen3.7-flash',8192,256)
        restarted._settle(identifier,{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120})
        restarted._settle(identifier,{'prompt_tokens':0,'completion_tokens':0,'total_tokens':0})
        restarted._reserve('qwen3.7-flash',8192,256)
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute("select units from budget_totals where scope='all'").fetchone()[0],18792)

    async def test_unknown_usage_keeps_reservation_and_oversized_usage_blocks_future_calls(self):
        budget = self.budget()
        identifier = budget._reserve('qwen3.7-flash',8192,256)
        budget._settle(identifier,None)
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('select units,status from model_attempts').fetchone(),(18432,'unknown_reserved'))
        budget._settle(identifier,{'prompt_tokens':10,'completion_tokens':257,'total_tokens':267})
        with self.assertRaises(BudgetUnavailable):
            self.budget()._reserve('text-embedding-v4',8192,0)

    async def test_daily_cap_applies_to_both_models(self):
        budget = self.budget(total='1',daily='0.005')
        budget._reserve('text-embedding-v4',8192,0)
        with self.assertRaises(BudgetUnavailable):
            budget._reserve('qwen3.7-flash',8192,256)

    async def test_http_usage_accounting_and_no_secrets_or_query_in_ledger(self):
        budget = self.budget()
        async with httpx.AsyncClient(base_url='https://dashscope.aliyuncs.com/compatible-mode/v1/',
            transport=httpx.MockTransport(lambda r:httpx.Response(200,json=completion('test description'))),
            event_hooks={'request':[budget.request],'response':[budget.response]}) as client:
            result = await BailianQueryRewriter(api_key='test-secret',http_client=client).rewrite('private-query-unique')
        self.assertEqual(result.status,'rewritten')
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute("select units from budget_totals where scope='all'").fetchone()[0],360)
        self.assertNotIn(b'test-secret',self.path.read_bytes())
        self.assertNotIn(b'private-query-unique',self.path.read_bytes())
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    async def test_unexpected_models_hosts_and_payloads_are_rejected_before_reservation(self):
        budget = self.budget()
        for url,body in [
            ('https://example.test/compatible-mode/v1/embeddings',{'model':'text-embedding-v4','input':['x'],'dimensions':1024}),
            ('https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings',{'model':'other','input':['x'],'dimensions':1024}),
            ('https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings',{'model':'text-embedding-v4','input':['x'*8193],'dimensions':1024}),
        ]:
            with self.assertRaises(BudgetUnavailable):
                await budget.request(httpx.Request('POST',url,json=body))
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('select count(*) from model_attempts').fetchone()[0],0)

    async def test_corrupt_ledger_fails_closed(self):
        self.path.write_bytes(b'not a database')
        with self.assertRaises(sqlite3.DatabaseError):
            self.budget()
        self.assertEqual(self.path.read_bytes(),b'not a database')

    async def test_inconsistent_ledger_is_not_silently_reset(self):
        budget = self.budget()
        budget._reserve('qwen3.7-flash',8192,256)
        with sqlite3.connect(self.path) as c:
            c.execute("delete from budget_totals where scope='all'")
        with self.assertRaisesRegex(ValueError,'inconsistent'):
            self.budget()

    async def test_currency_parsing_rejects_invalid_values(self):
        self.assertEqual(money_units('0.0000001'),1)
        for value in ('NaN','Infinity','-1','0.00000001','bad'):
            with self.assertRaises(ValueError):
                money_units(value)
