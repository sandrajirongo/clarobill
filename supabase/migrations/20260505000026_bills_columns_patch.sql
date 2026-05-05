-- Idempotent patch: catch up columns and objects that were skipped when their
-- source migrations were bypassed (pre-existing tables caused early failure
-- and PostgreSQL rolled back the entire migration transaction).
--
-- Source migrations and what they add:
--   20260416000013: profile_member_id, payer_name, plan_name, confirmed_at
--   20260420000017: ncci_edit_pairs service_type + payer_type, bills plan_type
--   20260420000019: file_path nullable (required for the upload-retry fix)
--   20260420000020: ncci_edit_pairs_service_payer_idx + delete_ncci_pairs RPC
--                   (marked applied without running because the columns it needs
--                   were rolled back with 20260420000017; content is here instead)

-- ─── ncci_edit_pairs: add service_type + payer_type (from 20260420000017) ────

ALTER TABLE public.ncci_edit_pairs
  ADD COLUMN IF NOT EXISTS service_type text NOT NULL DEFAULT 'practitioner'
    CHECK (service_type IN ('practitioner', 'outpatient', 'dme')),
  ADD COLUMN IF NOT EXISTS payer_type text NOT NULL DEFAULT 'medicare'
    CHECK (payer_type IN ('medicare', 'medicaid'));

-- Replace the (col1, col2) unique constraint with the wider (col1, col2, service, payer) one.
ALTER TABLE public.ncci_edit_pairs
  DROP CONSTRAINT IF EXISTS ncci_edit_pairs_column_one_code_column_two_code_key;

DO $$ BEGIN
  ALTER TABLE public.ncci_edit_pairs
    ADD CONSTRAINT ncci_edit_pairs_unique
      UNIQUE (column_one_code, column_two_code, service_type, payer_type);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ─── ncci_edit_pairs index + RPC (from 20260420000020) ───────────────────────

CREATE INDEX IF NOT EXISTS ncci_edit_pairs_service_payer_idx
  ON public.ncci_edit_pairs (service_type, payer_type);

CREATE OR REPLACE FUNCTION public.delete_ncci_pairs(
  p_service_type text,
  p_payer_type   text
) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
SET statement_timeout = '300s'
SET search_path = public
AS $$
DECLARE
  deleted_count integer;
BEGIN
  DELETE FROM public.ncci_edit_pairs
  WHERE service_type = p_service_type
    AND payer_type   = p_payer_type;
  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$;

-- ─── bills: file_path nullable (from 20260420000019) ─────────────────────────

-- file_path was NOT NULL in the initial schema; drop that so the upload
-- route can use null as a collision-free placeholder.
ALTER TABLE public.bills
  ALTER COLUMN file_path DROP NOT NULL;

ALTER TABLE public.bills
  ADD COLUMN IF NOT EXISTS profile_member_id uuid REFERENCES public.profile_members(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS payer_name        text,
  ADD COLUMN IF NOT EXISTS plan_name         text,
  ADD COLUMN IF NOT EXISTS confirmed_at      timestamptz,
  ADD COLUMN IF NOT EXISTS plan_type         text
    CHECK (plan_type IN ('commercial', 'medicare', 'medicaid', 'tricare', 'self_pay'));

CREATE INDEX IF NOT EXISTS bills_profile_member_id_idx ON public.bills (profile_member_id);

ALTER TABLE public.profile_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.insurance_plans ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  CREATE POLICY "profile_members: user isolation"
    ON public.profile_members FOR ALL
    USING (auth.uid() = user_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE POLICY "insurance_plans: user isolation"
    ON public.insurance_plans FOR ALL
    USING (
      EXISTS (
        SELECT 1 FROM public.profile_members
        WHERE profile_members.id = insurance_plans.profile_member_id
          AND profile_members.user_id = auth.uid()
      )
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
