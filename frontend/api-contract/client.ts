import type {
  LookupResponse, SuggestResponse, EntryResponse, SenseExamplesResponse,
  SemanticResponse, SemanticSearchRequest,
} from './types';

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, public retryAfter: number | null) {
    super(`Dictionary API returned ${status}`);
  }
}

export interface EntryPagination {
  sense_offset?: number; sense_limit?: number;
  form_offset?: number; form_limit?: number;
  example_offset?: number; example_limit?: number;
  expression_offset?: number; expression_limit?: number;
}

/** No automatic retry: semantic requests can incur provider charges. */
export class LexiconClient {
  constructor(private baseUrl = '', private mockScenario?: string) {}

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers);
    if (options.body) headers.set('Content-Type', 'application/json');
    if (this.mockScenario) headers.set('X-Mock-Scenario', this.mockScenario);
    const response = await fetch(this.baseUrl.replace(/\/$/, '') + path, { ...options, headers });
    const contentType = response.headers.get('Content-Type') || '';
    const body = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) {
      const retry = Number(response.headers.get('Retry-After'));
      throw new ApiError(response.status, typeof body === 'object' && body !== null ? body.detail : body,
        response.headers.has('Retry-After') && Number.isFinite(retry) ? retry : null);
    }
    return body as T;
  }

  lookup(q: string, signal?: AbortSignal, limit = 5) {
    return this.request<LookupResponse>('/lookup?' + new URLSearchParams({ q, limit: String(limit) }), { signal });
  }
  suggest(q: string, signal?: AbortSignal, limit = 10) {
    return this.request<SuggestResponse>('/suggest?' + new URLSearchParams({ q, limit: String(limit) }), { signal });
  }
  entry(lemmaId: number, pagination: EntryPagination = {}, signal?: AbortSignal) {
    const query = new URLSearchParams(Object.entries(pagination).filter(([, value]) => value !== undefined)
      .map(([key, value]) => [key, String(value)]));
    return this.request<EntryResponse>(`/entries/${lemmaId}` + (query.size ? `?${query}` : ''), { signal });
  }
  examples(senseId: number, offset = 0, limit = 10, signal?: AbortSignal) {
    return this.request<SenseExamplesResponse>(`/senses/${senseId}/examples?offset=${offset}&limit=${limit}`, { signal });
  }
  semantic(input: SemanticSearchRequest, signal?: AbortSignal) {
    return this.request<SemanticResponse>('/semantic-search', { method: 'POST', body: JSON.stringify(input), signal });
  }
}
