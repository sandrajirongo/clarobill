import { supabase } from '../supabase';

const API_URL = process.env.EXPO_PUBLIC_API_URL;
if (!API_URL) {
  throw new Error(
    'Missing EXPO_PUBLIC_API_URL. Copy apps/mobile/.env.example to apps/mobile/.env.local and fill it in.'
  );
}

/**
 * Error thrown by `apiFetch` when the API returns a non-2xx status.
 * Carries the parsed `ApiErrorResponse` payload from the server when available
 * so callers can branch on the `code` field instead of grepping strings.
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    public detail: string,
    public raw?: unknown,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

type FetchOptions = Omit<RequestInit, 'body' | 'headers'> & {
  body?: unknown; // any JSON-serialisable value; pass undefined for GET
  headers?: Record<string, string>;
};

/**
 * Authenticated fetch wrapper for ClaroBill API endpoints.
 *
 * - Resolves the current Supabase session and attaches `Authorization: Bearer`.
 * - Serialises JSON bodies, sets the Content-Type header.
 * - Throws `ApiError` on non-2xx so callers don't need to manually re-check `.ok`.
 */
export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers ?? {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const { body, headers: _ignoredHeaders, ...rest } = options;
  const init: RequestInit = { ...rest, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  const url = path.startsWith('http') ? path : `${API_URL}${path}`;
  const response = await fetch(url, init);

  if (!response.ok) {
    let code = 'API_ERROR';
    let detail = `${response.status} ${response.statusText}`;
    let raw: unknown;
    try {
      raw = await response.json();
      if (raw && typeof raw === 'object' && 'error' in raw) {
        const err = (raw as { error: { code?: string; detail?: string } }).error;
        code = err.code ?? code;
        detail = err.detail ?? detail;
      }
    } catch {
      // Non-JSON error body — keep status text as detail
    }
    throw new ApiError(response.status, code, detail, raw);
  }

  // 204 No Content
  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}
