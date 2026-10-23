"""Durable, shared reservations for online model calls; never stores query text.

All amounts are integer units of 0.0000001 CNY. Pending/uncertain attempts
retain their maximum reservation across restarts. This is separate from the
offline index-builder budget and the provider's account billing balance.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


class BudgetUnavailable(ValueError):
    pass


def money_units(value: str) -> int:
    try:
        number = Decimal(value)
        units = number * 10_000_000
        if not number.is_finite() or number < 0 or units != units.to_integral_value():
            raise ValueError
        return int(units)
    except (InvalidOperation, ValueError, OverflowError):
        raise ValueError('Budget must be nonnegative CNY with at most 7 decimal places') from None


class OnlineModelBudget:
    # Beijing short-input list prices, checked 2026-10-23. No free-credit assumption.
    PRICES = {'qwen3.7-flash': (2, 8), 'text-embedding-v4': (5, 0)}

    def __init__(self, path: str, *, total_cny: str, daily_cny: str):
        self.path = Path(path)
        self.total_cap = money_units(total_cny)
        self.daily_cap = money_units(daily_cny)
        if self.total_cap and self.daily_cap:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.path.is_symlink():
                raise ValueError('Budget ledger must not be a symlink')
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            self.path.chmod(0o600)
            with self._connection() as c:
                c.executescript('''
                    create table if not exists budget_metadata(version text primary key);
                    insert or ignore into budget_metadata values('online-v1-beijing-20261023');
                    create table if not exists budget_totals(scope text primary key, units integer not null);
                    create table if not exists budget_faults(reason text primary key);
                    create table if not exists model_attempts(
                        id text primary key, day text not null, model text not null,
                        input_bound integer not null, output_bound integer not null,
                        units integer not null, status text not null,
                        prompt_tokens integer, completion_tokens integer);
                ''')
                c.execute('begin immediate')
                if c.execute('select version from budget_metadata').fetchall() != [('online-v1-beijing-20261023',)]:
                    raise ValueError('Unsupported budget ledger version')
                expected = dict(c.execute('select day, sum(units) from model_attempts group by day'))
                expected['all'] = sum(expected.values())
                actual = dict(c.execute('select scope, units from budget_totals'))
                if {k:v for k,v in expected.items() if v} != {k:v for k,v in actual.items() if v}:
                    raise ValueError('Budget ledger totals are inconsistent')

    @contextmanager
    def _connection(self):
        c = sqlite3.connect(self.path, timeout=0.1)
        try:
            c.execute('pragma synchronous=FULL')
            with c:
                yield c
        finally:
            c.close()

    def _reserve(self, model: str, input_bound: int, output_bound: int) -> str:
        if not self.total_cap or not self.daily_cap:
            raise BudgetUnavailable('Online model budget has not been configured')
        units = input_bound * self.PRICES[model][0] + output_bound * self.PRICES[model][1]
        day = datetime.now(timezone.utc).date().isoformat()
        identifier = uuid.uuid4().hex
        try:
            with self._connection() as c:
                c.execute('begin immediate')
                if c.execute('select 1 from budget_faults limit 1').fetchone():
                    raise BudgetUnavailable('Online model budget requires review')
                used = dict(c.execute('select scope, units from budget_totals where scope in (?,?)', ('all',day)))
                if used.get('all',0)+units > self.total_cap or used.get(day,0)+units > self.daily_cap:
                    raise BudgetUnavailable('Online model budget reached')
                c.execute('insert into model_attempts values(?,?,?,?,?,?,?,null,null)',
                          (identifier,day,model,input_bound,output_bound,units,'pending_or_unknown'))
                for scope in ('all',day):
                    c.execute('insert into budget_totals values(?,?) on conflict(scope) do update set units=units+excluded.units',
                              (scope,units))
            return identifier
        except (sqlite3.Error, OSError):
            raise BudgetUnavailable('Online model budget ledger is unavailable') from None

    def _settle(self, identifier: str, usage: dict | None):
        try:
            with self._connection() as c:
                c.execute('begin immediate')
                row = c.execute('select day,model,input_bound,output_bound,units,status from model_attempts where id=?',
                                (identifier,)).fetchone()
                if row is None or row[5] == 'usage_confirmed':
                    return
                day,model,input_bound,output_bound,reserved,_ = row
                prompt = usage.get('prompt_tokens') if isinstance(usage,dict) else None
                completion = usage.get('completion_tokens',0) if isinstance(usage,dict) else None
                total = usage.get('total_tokens') if isinstance(usage,dict) else None
                valid = (type(prompt) is int and type(completion) is int
                         and 0 <= prompt <= input_bound and 0 <= completion <= output_bound
                         and (total is None or (type(total) is int and total == prompt+completion)))
                if not valid:
                    if ((type(prompt) is int and prompt > input_bound)
                        or (type(completion) is int and completion > output_bound)):
                        c.execute("insert or ignore into budget_faults values('provider_usage_exceeded_reservation')")
                    c.execute("update model_attempts set status='unknown_reserved' where id=?", (identifier,))
                    return
                actual = prompt*self.PRICES[model][0] + completion*self.PRICES[model][1]
                c.execute("update model_attempts set units=?,status='usage_confirmed',prompt_tokens=?,completion_tokens=? where id=?",
                          (actual,prompt,completion,identifier))
                for scope in ('all',day):
                    c.execute('update budget_totals set units=units+? where scope=?', (actual-reserved,scope))
        except (sqlite3.Error, OSError):
            raise BudgetUnavailable('Online model budget ledger is unavailable') from None

    async def request(self, request):
        try:
            host = request.url.host
            if (request.url.scheme != 'https'
                or not (host == 'dashscope.aliyuncs.com' or host.endswith('.cn-beijing.maas.aliyuncs.com'))
                or not request.url.path.startswith('/compatible-mode/v1/') or request.url.query):
                raise ValueError
            body = json.loads(request.content)
            model = body['model']
            if model == 'qwen3.7-flash':
                if (not request.url.path.endswith('/chat/completions')
                    or len(request.content)>4096 or body.get('enable_thinking') is not False
                    or body.get('max_completion_tokens') != 256 or body.get('stream') is not False):
                    raise ValueError
                input_bound, output_bound = 8192, 256
            elif model == 'text-embedding-v4':
                texts = body['input']
                if (not request.url.path.endswith('/embeddings') or body.get('dimensions') != 1024
                    or not isinstance(texts,list) or not 1 <= len(texts) <= 10
                    or any(not isinstance(t,str) or len(t.encode('utf-8'))>8192 for t in texts)):
                    raise ValueError
                input_bound, output_bound = 8192*len(texts), 0
            else:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise BudgetUnavailable('Unexpected online model request') from None
        request.extensions['online_budget_id'] = await asyncio.to_thread(self._reserve, model, input_bound, output_bound)

    async def response(self, response):
        await response.aread()
        usage = None
        if response.is_success:
            try:
                usage = response.json().get('usage')
            except (ValueError, AttributeError):
                pass
        await asyncio.to_thread(self._settle, response.request.extensions['online_budget_id'], usage)
