export class ApiError extends Error {
    status;
    detail;
    retryAfter;
    constructor(status, detail, retryAfter) {
        super(`Dictionary API returned ${status}`);
        this.status = status;
        this.detail = detail;
        this.retryAfter = retryAfter;
    }
}
/** No automatic retry: semantic requests can incur provider charges. */
export class LexiconClient {
    baseUrl;
    mockScenario;
    constructor(baseUrl = '', mockScenario) {
        this.baseUrl = baseUrl;
        this.mockScenario = mockScenario;
    }
    async request(path, options = {}) {
        const headers = new Headers(options.headers);
        if (options.body)
            headers.set('Content-Type', 'application/json');
        if (this.mockScenario)
            headers.set('X-Mock-Scenario', this.mockScenario);
        const response = await fetch(this.baseUrl.replace(/\/$/, '') + path, { ...options, headers });
        const contentType = response.headers.get('Content-Type') || '';
        const body = contentType.includes('application/json') ? await response.json() : await response.text();
        if (!response.ok) {
            const retry = Number(response.headers.get('Retry-After'));
            throw new ApiError(response.status, typeof body === 'object' && body !== null ? body.detail : body, response.headers.has('Retry-After') && Number.isFinite(retry) ? retry : null);
        }
        return body;
    }
    lookup(q, signal, limit = 5) {
        return this.request('/lookup?' + new URLSearchParams({ q, limit: String(limit) }), { signal });
    }
    suggest(q, signal, limit = 10) {
        return this.request('/suggest?' + new URLSearchParams({ q, limit: String(limit) }), { signal });
    }
    entry(lemmaId, pagination = {}, signal) {
        const query = new URLSearchParams(Object.entries(pagination).filter(([, value]) => value !== undefined)
            .map(([key, value]) => [key, String(value)]));
        return this.request(`/entries/${lemmaId}` + (query.size ? `?${query}` : ''), { signal });
    }
    examples(senseId, offset = 0, limit = 10, signal) {
        return this.request(`/senses/${senseId}/examples?offset=${offset}&limit=${limit}`, { signal });
    }
    semantic(input, signal) {
        return this.request('/semantic-search', { method: 'POST', body: JSON.stringify(input), signal });
    }
}
