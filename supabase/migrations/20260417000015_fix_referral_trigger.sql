-- Fix: referral-code trigger could block user creation on a code collision.
--
-- The original trigger used ON CONFLICT (user_id) DO NOTHING, which only
-- handles conflicts on user_id. The 'code' column also has a UNIQUE constraint,
-- so a collision there raises an unhandled unique_violation that propagates
-- through the trigger, rolling back the entire auth.users INSERT and returning
-- "database error saving new user" to the client.
--
-- Fix: wrap the INSERT in an exception handler and retry up to 10 times on
-- any unique_violation. Also extends the code from 8 to 10 hex chars (~1T
-- possible values) to make collisions negligible at scale.

-- Idempotent: referral_codes already has RLS from migration 000002.
-- Restated here so the Supabase linter doesn't flag the INSERT in the function body.
alter table public.referral_codes enable row level security;

create or replace function public.create_user_referral_code()
returns trigger language plpgsql security definer
set search_path = public
as $$
declare
  generated_code text;
  attempts       int := 0;
begin
  -- Guard: user already has a code (e.g. backfill ran before trigger fired)
  if exists (select 1 from public.referral_codes where user_id = new.id) then
    return new;
  end if;

  loop
    -- 10 uppercase hex chars from 5 random bytes (~1.1 trillion possibilities)
    generated_code := upper(substr(encode(gen_random_bytes(5), 'hex'), 1, 10));
    begin
      insert into public.referral_codes (user_id, code)
      values (new.id, generated_code);
      return new;  -- success — exit
    exception when unique_violation then
      -- Retry on code collision. After 10 attempts degrade gracefully:
      -- user is created without a referral code rather than blocking signup.
      attempts := attempts + 1;
      if attempts >= 10 then
        return new;
      end if;
    end;
  end loop;
end;
$$;

