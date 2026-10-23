"""Bounded per-client sliding windows for the single-worker search deployment.

Use the ASGI client address, never arbitrary forwarding headers. Uvicorn may
resolve that address only from explicitly trusted reverse proxies.
"""
from __future__ import annotations

import ipaddress
import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field


@dataclass
class ClientWindow:
    requests: deque = field(default_factory=deque)
    semantic: deque = field(default_factory=deque)
    last_seen: float = 0


class IPRateLimiter:
    def __init__(self, per_minute=60, semantic_per_minute=10, burst=10,
                 max_clients=10000, clock=time.monotonic):
        if min(per_minute, semantic_per_minute, burst, max_clients) < 1:
            raise ValueError("Rate limits must be positive")
        self.per_minute = per_minute
        self.semantic_per_minute = semantic_per_minute
        self.burst = burst
        self.max_clients = max_clients
        self.clock = clock
        self.clients: OrderedDict[str, ClientWindow] = OrderedDict()

    def check(self, client: str, semantic=False) -> int:
        """Consume one request, or return Retry-After seconds. No await/races."""
        try:
            addr = ipaddress.ip_address(client)
            client = str(getattr(addr, "ipv4_mapped", None) or addr)
        except ValueError:
            pass
        now = self.clock()
        while self.clients:
            oldest = next(iter(self.clients))
            if now - self.clients[oldest].last_seen < 60:
                break
            self.clients.popitem(last=False)
        if client not in self.clients:
            # Never evict an active client's quota to make room for attackers.
            if len(self.clients) >= self.max_clients:
                return 60
            self.clients[client] = ClientWindow()
        state = self.clients[client]
        state.last_seen = now
        self.clients.move_to_end(client)
        for queue in (state.requests, state.semantic):
            while queue and queue[0] <= now - 60:
                queue.popleft()
        waits = []
        if len(state.requests) >= self.per_minute:
            waits.append(state.requests[0] + 60 - now)
        recent = [t for t in state.requests if t > now - 10]
        if len(recent) >= self.burst:
            waits.append(recent[0] + 10 - now)
        if semantic and len(state.semantic) >= self.semantic_per_minute:
            waits.append(state.semantic[0] + 60 - now)
        if waits:
            return max(1, math.ceil(max(waits)))
        state.requests.append(now)
        if semantic:
            state.semantic.append(now)
        return 0


class QueryLimitMiddleware:
    def __init__(self, app, limiter, max_body_bytes=8192):
        self.app = app
        self.limiter = limiter
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        from starlette.responses import JSONResponse

        path = scope.get('path', '')
        is_query = (path in {'/lookup', '/suggest', '/semantic-search'}
                    or path.startswith('/entries/') or path.startswith('/senses/'))
        if scope['type'] != 'http' or not is_query:
            return await self.app(scope, receive, send)
        client = (scope.get('client') or ('unknown', 0))[0]
        retry = self.limiter.check(client, scope['path'] == '/semantic-search')
        if retry:
            response = JSONResponse({'detail': 'Too many queries. Please retry later.'},
                                    status_code=429, headers={'Retry-After': str(retry),
                                                            'Cache-Control': 'no-store'})
            return await response(scope, receive, send)
        # Bound chunked bodies as well as requests with Content-Length.
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > self.max_body_bytes:
                return await JSONResponse({'detail': 'Request body too large'}, status_code=413)(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False
        async def bounded_receive():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
        return await self.app(scope, bounded_receive, send)
