create table if not exists public.cms_hcpcs_codes (
    id                  uuid    primary key default gen_random_uuid(),
    effective_from      date    not null,
    hcpc                text    not null,
    short_description   text,
    long_description    text,
    pricing_indicator   text,   -- pos 120-121: 00=not separately priced, 11=RVU, 12=anesthesia, etc.
    coverage_code       text,   -- pos 230: I=not payable, M=non-covered, S=non-covered by statute
    termination_date    date,   -- pos 285-292: last valid date for this code (null = still active)
    action_code         text,   -- pos 293: A=added, D=discontinued, N=no change, R=reactivated
    is_noc              boolean not null default false,  -- "not otherwise classified/specified"

    unique (effective_from, hcpc)
);

create index cms_hcpcs_codes_lookup_idx
    on public.cms_hcpcs_codes (hcpc, effective_from desc);

-- RLS enabled; no policy — engine reads via service role (bypasses RLS).
alter table public.cms_hcpcs_codes enable row level security;
