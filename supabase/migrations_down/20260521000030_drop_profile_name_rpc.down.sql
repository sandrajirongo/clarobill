create or replace function public.update_user_profile_name(
  p_user_id    uuid,
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

revoke execute on function public.update_user_profile_name(uuid, text, text) from public, anon, authenticated;
grant  execute on function public.update_user_profile_name(uuid, text, text) to service_role;
