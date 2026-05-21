import { describe, expect, it, vi, beforeEach } from 'vitest';
import { PATCH } from '../route';

const mockEq = vi.fn();
const mockUpdate = vi.fn().mockReturnValue({ eq: mockEq });
const mockFrom = vi.fn().mockReturnValue({ update: mockUpdate });

vi.mock('@/lib/supabase/server', () => ({
  getAuthenticatedUser: vi.fn(),
  createSupabaseServerClient: vi.fn(async () => ({ from: mockFrom })),
}));

vi.mock('@/lib/loops', () => ({
  updateLoopsContact: vi.fn().mockResolvedValue(undefined),
}));

import { getAuthenticatedUser } from '@/lib/supabase/server';

const mockAuth = vi.mocked(getAuthenticatedUser);
const fakeUser = { id: 'u-abc', email: 'patient@test.com' } as ReturnType<typeof getAuthenticatedUser> extends Promise<infer T> ? NonNullable<T> : never;

function req(body: unknown): Request {
  return new Request('http://localhost/api/user/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('PATCH /api/user/profile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockEq.mockResolvedValue({ error: null });
  });

  it('returns 401 when unauthenticated', async () => {
    mockAuth.mockResolvedValue(null);
    const res = await PATCH(req({ first_name: 'Jane', last_name: 'Doe' }));
    expect(res.status).toBe(401);
  });

  it('returns 400 for malformed JSON', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    const badReq = new Request('http://localhost/api/user/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: 'not-json',
    });
    const res = await PATCH(badReq);
    expect(res.status).toBe(400);
  });

  it('returns 400 when first_name is not a string or null', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    const res = await PATCH(req({ first_name: 123, last_name: 'Doe' }));
    expect(res.status).toBe(400);
  });

  it('returns 200 with { ok: true } on successful save', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    const res = await PATCH(req({ first_name: 'Jane', last_name: 'Doe' }));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ok: true });
  });

  it('updates first_name and last_name scoped to the authenticated user', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    await PATCH(req({ first_name: 'Jane', last_name: 'Doe' }));
    expect(mockUpdate).toHaveBeenCalledWith({ first_name: 'Jane', last_name: 'Doe' });
    expect(mockEq).toHaveBeenCalledWith('id', 'u-abc');
  });

  it('accepts null names', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    const res = await PATCH(req({ first_name: null, last_name: null }));
    expect(res.status).toBe(200);
    expect(mockUpdate).toHaveBeenCalledWith({ first_name: null, last_name: null });
  });

  it('returns 500 with generic message when update fails', async () => {
    mockAuth.mockResolvedValue(fakeUser);
    mockEq.mockResolvedValue({ error: { code: '42P01', message: 'relation "user_profiles" does not exist' } });
    const res = await PATCH(req({ first_name: 'Jane', last_name: null }));
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error.code).toBe('DB_ERROR');
    expect(body.error.detail).not.toContain('relation');
    expect(body.error.detail).not.toContain('does not exist');
  });
});
