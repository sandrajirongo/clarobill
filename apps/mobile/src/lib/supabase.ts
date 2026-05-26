import { createClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

// SecureStore has a 2048-byte per-key limit on iOS. Supabase session tokens
// regularly exceed that, so we split the value across N chunks keyed by index.
// Reads reassemble the chunks in order; writes wipe any stale extra chunks.
const CHUNK_SIZE = 1800;

const LargeSecureStore = {
  async getItem(key: string): Promise<string | null> {
    const head = await SecureStore.getItemAsync(key);
    if (!head) return null;

    // Legacy format: value stored under the single key (pre-chunking)
    if (!head.startsWith('__chunked__:')) return head;

    const count = Number.parseInt(head.slice('__chunked__:'.length), 10);
    if (!Number.isFinite(count) || count <= 0) return null;

    const parts = await Promise.all(
      Array.from({ length: count }, (_, i) => SecureStore.getItemAsync(`${key}__${i}`))
    );
    if (parts.some((p) => p === null)) return null;
    return parts.join('');
  },

  async setItem(key: string, value: string): Promise<void> {
    // Wipe any prior chunks before writing — prevents a partial-old, partial-new state
    await LargeSecureStore.removeItem(key);

    if (value.length <= CHUNK_SIZE) {
      await SecureStore.setItemAsync(key, value);
      return;
    }

    const chunks: string[] = [];
    for (let i = 0; i < value.length; i += CHUNK_SIZE) {
      chunks.push(value.slice(i, i + CHUNK_SIZE));
    }
    await Promise.all(
      chunks.map((chunk, i) => SecureStore.setItemAsync(`${key}__${i}`, chunk))
    );
    await SecureStore.setItemAsync(key, `__chunked__:${chunks.length}`);
  },

  async removeItem(key: string): Promise<void> {
    const head = await SecureStore.getItemAsync(key);
    if (head?.startsWith('__chunked__:')) {
      const count = Number.parseInt(head.slice('__chunked__:'.length), 10);
      if (Number.isFinite(count) && count > 0) {
        await Promise.all(
          Array.from({ length: count }, (_, i) => SecureStore.deleteItemAsync(`${key}__${i}`))
        );
      }
    }
    await SecureStore.deleteItemAsync(key);
  },
};

const supabaseUrl = process.env.EXPO_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    'Missing EXPO_PUBLIC_SUPABASE_URL or EXPO_PUBLIC_SUPABASE_ANON_KEY. Copy apps/mobile/.env.example to apps/mobile/.env.local and fill in the values.'
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    storage: LargeSecureStore,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false, // mobile uses deep links, not URL hashes
  },
});
