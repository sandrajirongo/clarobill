-- Fix: create_user_referral_code() used gen_random_bytes() which requires the
-- pgcrypto extension. pgcrypto was not enabled on the project, causing every
-- new user creation to fail with "function gen_random_bytes(integer) does not
-- exist", rolling back the auth.users INSERT and returning "database error
-- saving new user" to the client.
--
-- Fix: replace gen_random_bytes(5) with gen_random_uuid(), which is built into
-- Postgres core (no extension required) and is equally cryptographically secure
-- for generating referral codes.

alter table public.referral_codes enable row level security;

create or replace function public.create_user_referral_code()
returns trigger language plpgsql security definer
set search_path = public
as $$
declare
  generated_code text;
  attempts       int := 0;
begin
  if exists (select 1 from public.referral_codes where user_id = new.id) then
    return new;
  end if;
  loop
    -- gen_random_uuid() is built-in (no pgcrypto needed); take 10 uppercase hex
    -- chars from the UUID's 32 hex digits (~1.1 trillion possible codes).
    generated_code := upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 10));
    begin
      insert into public.referral_codes (user_id, code)
      values (new.id, generated_code);
      return new;
    exception when unique_violation then
      attempts := attempts + 1;
      if attempts >= 10 then
        return new;
      end if;
    end;
  end loop;
end;
$$;
