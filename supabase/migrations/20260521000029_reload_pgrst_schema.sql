-- Force PostgREST to reload its schema cache.
--
-- first_name and last_name were added to user_profiles in 20260511000027,
-- and update_user_profile_name() was added in 20260521000028, but PostgREST
-- was never signalled to reload after either migration was applied. As a
-- result PostgREST silently drops those columns from every REST call.
--
-- This statement is idempotent — sending the notification multiple times
-- is harmless. It fires on transaction commit.
notify pgrst, 'reload schema';
