-- RPC to update first_name/last_name on user_profiles.
-- Using an RPC bypasses PostgREST's column-level schema cache, which does not
-- automatically pick up columns added via ALTER TABLE until PostgREST restarts.
-- The function is SECURITY DEFINER so it runs with full table access regardless
-- of the caller's role, matching the intent of the service-client UPDATE it replaces.
create or replace function public.update_user_profile_name(
  p_user_id   uuid,
  p_first_name text,
  p_last_name  text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.user_profiles
  set
    first_name = p_first_name,
    last_name  = p_last_name,
    updated_at = now()
  where id = p_user_id;
end;
$$;

-- Only the service role should call this function — anon/authenticated roles
-- must go through the RLS-gated table directly.
revoke execute on function public.update_user_profile_name(uuid, text, text) from public, anon, authenticated;
grant  execute on function public.update_user_profile_name(uuid, text, text) to service_role;
