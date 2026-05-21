-- Drop the update_user_profile_name RPC added in 20260521000028.
-- The function was never called — the route was switched back to a direct
-- UPDATE via the authenticated server client before the RPC was ever used.
drop function if exists public.update_user_profile_name(uuid, text, text);
