-- Rollback: 20260416000013_profile_members_insurance

alter table public.bills
  drop column if exists profile_member_id,
  drop column if exists payer_name,
  drop column if exists plan_name,
  drop column if exists confirmed_at;

drop table if exists public.insurance_plans;
drop table if exists public.profile_members;
