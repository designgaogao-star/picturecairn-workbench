import type { paths } from './schema';

type Method = 'get' | 'post' | 'put' | 'patch' | 'delete';
type Routes<M extends Method> = { [P in keyof paths]: M extends keyof paths[P] ? P : never }[keyof paths];
type Operation<P extends keyof paths, M extends Method> = M extends keyof paths[P] ? NonNullable<paths[P][M]> : never;
type JsonBody<O> = O extends { requestBody: { content: { 'application/json': infer B } } } ? B : never;
type Parameters<O> = O extends { parameters: infer P } ? P : never;
type JsonResponse<O> = O extends { responses: infer R } ? {
  [S in Extract<keyof R, 200 | 201 | 202 | 204>]: R[S] extends { content: { 'application/json': infer B } } ? B : S extends 204 ? void : never
}[Extract<keyof R, 200 | 201 | 202 | 204>] : never;

export class GalleryClient {
  constructor(readonly baseUrl: string = '', private readonly fetcher: typeof fetch = (...args) => fetch(...args)) {}

  async request<M extends Method, P extends Routes<M>>(
    method: M, route: P,
    options: { params?: Parameters<Operation<P, M>>; body?: JsonBody<Operation<P, M>>; signal?: AbortSignal } = {},
  ): Promise<JsonResponse<Operation<P, M>>> {
    let path: string = route;
    const params = options.params as { path?: Record<string, unknown>; query?: Record<string, unknown> } | undefined;
    for (const [key, value] of Object.entries(params?.path || {})) path = path.replace(`{${key}}`, encodeURIComponent(String(value)));
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params?.query || {})) if (value !== undefined && value !== null) query.set(key, String(value));
    const url = this.baseUrl + path + (query.size ? '?' + query : '');
    const response = await this.fetcher(url, { method: method.toUpperCase(), signal: options.signal,
      headers: options.body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: options.body === undefined ? undefined : JSON.stringify(options.body) });
    if (!response.ok) throw new GalleryError(response.status, await response.json().catch(() => ({})));
    return (response.status === 204 ? undefined : await response.json()) as JsonResponse<Operation<P, M>>;
  }

  thumbnail(imageId: string, edge: 400 | 800 | 1600 | 2560 | 4200 = 400, version?: string): string {
    return `${this.baseUrl}/api/v1/images/${encodeURIComponent(imageId)}/thumbnail?edge=${edge}${version ? '&version=' + encodeURIComponent(version) : ''}`;
  }

  original(imageId: string): string { return `${this.baseUrl}/api/v1/images/${encodeURIComponent(imageId)}/original`; }

  events(): EventSource { return new EventSource(this.baseUrl + '/api/v1/events'); }
}

export class GalleryError extends Error {
  constructor(readonly status: number, readonly detail: unknown) { super(`Gallery API returned ${status}`); }
}
