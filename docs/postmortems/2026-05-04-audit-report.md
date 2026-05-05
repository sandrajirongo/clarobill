ClaroBill — Full-Codebase Audit Report (2026-05-04)                                                                                      
                                                                                                
TL;DR                                                                                                                                    
                                                                                                
29 findings across 4 audits. 5 are production-stopping, 11 are high-severity bugs, 13 are medium. Plus 3 regression-gate breakages.      
                                                                                                
The codebase passes type-checking and most lint, but several dynamic correctness gates (frontend tests, engine pytest) are broken or
missing entirely. The core billing-detection logic has 3 critical math/parser bugs that produce wrong dollar amounts in patient-facing   
reports. The MRF discovery pipeline has 4 silent-failure modes that can quietly burn budget and mark hospitals as permanently failed. The
frontend↔engine type boundary is documented but not enforced — Zod is installed and never used; 13 unsafe as casts paper over real shape
mismatches.                                                                              
                                                                                                                                        
---                                                                                            
⛔ Stop-the-line bugs (fix before next bill is processed)                                                                                
                                                                                        
S1. BillingError snake_case/camelCase mismatch — patient report will crash on first real finding                                         
                                                                                                
Files: apps/engine/app/api/v1/bills.py:335 (writer) ↔ apps/web/src/app/dashboard/bills/[billId]/page.tsx:148 (reader)            
The engine writes e.model_dump() (snake_case keys) into the analysis_results.errors JSONB column. The frontend reads itas BillingError[]
(camelCase) via an as cast. error.estimatedOvercharge and error.affectedLineItemIds will be undefined whenever a real finding is
emitted. The rules engine evidently has not yet emitted any findings against a real bill in production, which is the only reason this
hasn't crashed yet.                                                                                                                      
Fix: Add model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True) on the BillingError model and dump with
by_alias=True. Alternative: explicit key-mapping at the persistence boundary. Half-day of work.                                          
                                                                                                                                        
S2. NCCI modifier-59 override is all-or-nothing — false negatives on legitimate unbundling                                               
                                                                                                                                        
File: apps/engine/app/services/rules_engine.py:521-524                                                                           
A single col2 line item with modifier 59 suppresses the NCCI flag for ALL other instances of that pair on the same bill. Per CMS,        
modifier 59 is per-line, not per-pair. Real impact: a bill with 5 unbundled procedures + 1 legitimate-distinct-site instance produces
zero findings instead of 4.                                                                                                              
Fix: Filter col2_indices to only those without override modifiers; continue only if filtered list is empty. Code patch is in the agent
report.                                                                                                                                  
                                                                                        
S3. Stage 4 _persist_results flush failure silently retains buffer + reports success                                                     
                                                                                                
File: scripts/mrf_discovery/stage4_extract_mrf_urls.py:1094-1102                                                                         
A BQ MERGE failure on flush 1 (schema drift, IAM revoke) compounds the buffer for every subsequent flush. The pipeline reports "Stage 4
complete" with total_flushed understated even when zero rows persisted. Sandra would see optimistic stats and re-crawl every hospital    
next run, silently re-billing for HEAD requests against thousands of websites.                                                           
Fix: Abort with non-zero exit after N consecutive flush failures; verify len(buffer) decreases monotonically; raise on the final-flush
failure path.                                                                                                                            
                                                                                                                                
S4. Stage 4 _crawl_hospital silently marks transient errors as permanent                                                                 
                                                                                                
File: scripts/mrf_discovery/stage4_extract_mrf_urls.py:1110-1114                                                                         
except Exception as exc logs only the bare message (no traceback), defaults result = [], and writes error_stage='stage4_no_mrf_found' +
crawl_complete_at=NOW(). Permanent. So a bug affecting 100 hospitals (unicode edge case in regex, transient threading issue) silently    
brands them as "no MRF found" forever. They never appear in any error count.                                                             
Fix: logger.exception(...). Use a separate error_stage='stage4_crawler_crashed' so transient crashes are retryable.              
                                                                                                                                        
S5. Stage 4 resp.text is unbounded — single 500MB hospital response can OOM the worker                                           
                                                                                                                                        
File: scripts/mrf_discovery/stage4_extract_mrf_urls.py:715                                     
No stream=True, no body-size cap. With 60 workers, three pathological responses can OOM the Cloud Run container. Container dies          
mid-flush, last 1000 hospitals' work is lost, no signal which hospital killed it. Compare to Stage 3 Tier 2 which correctly does
resp.raw.read(65536).                                                                                                                    
Fix: stream=True + resp.raw.read(5_000_000).                                                                                             
                                                                                                                                        
---                                                                                                                                      
🔥 High-severity bugs                                                                                                                    
                                                                                                                            
H1. ZIP code captured as CPT code when address has no comma                                                                              
                                                                                                                                
parser.py:285 — exclusion regex requires comma but the hospital-address pattern allows commaless format. "Cleveland OH 44195" produces a 
fake "44195" CPT, which pollutes line-items and breaks downstream rules.                                                                 
                                                                                                                                
H2. Mileage rounding loses precision                                                                                                     
                                                                                                                                
parser.py:323-324 — unit_charge = round(charge / miles, 2) then total_charge = charge. Rules engine computes overcharge against the
rounded unit. Drifts up to $0.50/mile × miles in patient-facing savings.                                                                 
                                                                                                                                        
H3. NCCI overcharge double-counts when same col2 bundles into multiple col1s                                                             
                                                                                                                                        
rules_engine.py:528-560 — docstring claims subsequent errors set overcharge=0; implementation never does. Each component code emits full
overcharge; report-level dedup can't collapse them because keys differ.                                                    
                                                                                                                                        
H4. Tier 3 Places API charges Sandra for failed network requests                                                                 
                                                                                                                                        
places_client.py:283-308 + stage3_tier3_places.py:485-497 — CostMeter increments BEFORE the request. Network errors return [] but cost is
still booked. Hospital is removed from pending_ccns so it's never retried, yet phantom-charged. Could silently drain $50-100 of budget
per run on hospitals Google never actually saw.                                                                                          
                                                                                                                                
H5. Stage 4 staging table prefix _stage4_* may be invalid in BQ                                                                          
                                                                                                                                        
stage4_extract_mrf_urls.py:851, 914 — leading underscore is reserved for system tables. The load-job API may reject this with BadRequest,
masked by the broad except in S3 above. Easy fix: drop the leading underscore.                                                          
                                                                                                                                
H6. Stage 1 CMS pagination has no hard cap                                                                                               
                                                                                                
stage1_cms_hospital_list.py:86-98 — if CMS returns wrong total, loop runs ~2 million page requests over 6 days. No abort. Add MAX_PAGES =
200.                                                                                          
                                                                                                                                        
H7. Tier 1 invalid-URL rows get permanently stuck                                         
                                                                                                                                        
stage3_tier1_validate_urls.py:282-288 — invalid URLs increment consecutive_failures but Tiers 2/3 query WHERE hospital_website IS NULL so
they never re-process. ~300 zombie hospitals re-validate the same bad URL forever.                                              
                                                                                                                                        
H8. Pydantic AnalysisResult Decimal fields lack JSON serializer                                                                  
                                                                                                                                        
apps/engine/app/models/bill.py:90-92 — Decimal dumps as JSON string, breaks TS number contract. Currently masked because the engine      
inserts hand-floated values into Supabase, but it's a footgun the moment anyone wires this as response_model=.                   
                                                                                                                                        
H9. NPI extraction has 1-in-10 false positive rate                                                                               
                                                                                                                                        
parser.py:182-185 — _NPI_CONTEXT_PATTERN with .{0,60} and Luhn check on arbitrary 10-digit numbers. Wrong NPI → wrong hospital → wrong   
negotiated rate → false NEGOTIATED_RATE_EXCEEDED critical errors with bogus dollar amounts in patient reports.                   
                                                                                                                                        
H10. AnalyzeRequest type accepts arbitrary strings for plan_type, state, zip_code                                                
                                                                                                                                        
apps/engine/app/models/bill.py:101-123 — PlanType literal exists in shared/, ignored by Pydantic request schema. No 5-digit ZIP          
constraint, no state validation.                                                                                                 
                                                                                                                                        
H11. Engine pytest collection is broken                                                                                          
                                                                                                                                        
2 test modules can't import — posthog package missing in .venv. 421 tests never run. (Regression-gate finding.)                          
                                                                                                                                
---                                                                                                                                      
🟡 Medium-severity issues                                                                                                        
                                                                                                                                        
M1. Web app has zero test files (vitest configured but unused) + missing jsdom dep                                                       
                                                                                                                                
apps/web — vitest is in package.json, no **/*.test.* exists. CLAUDE.md Rule 8 says "every service function has a corresponding test."    
Frontend has zero test coverage.                                                                                                 
                                                                                                                                        
M2. Ruff: 2 errors (N806 uppercase locals)                                                     
                                                                                                                                
ai_analysis.py:308, report_generator.py:85 — trivial fix, but breaks regression-gate.          
                                                                                                                                        
M3. Anesthesia time pattern over-matches "5 min" in unrelated text                                                                       
                                                                                                                                        
parser.py:132 — any "X min" within 3 lines of an anesthesia code attaches as bogus time, breaking the entire ANESTHESIA_OUTLIER          
calculation.                                                                                                                             
                                                                                                                            
M4. Severity sort key relies on .lower() for what should be a typed enum                                                                 
                                                                                                                                
report_generator.py:88 — rules engine emits raw strings bypassing ErrorSeverity StrEnum. New severity values silently bucket at position 
9.                                                                                             
                                                                                                                                        
M5. Charge regex picks up date fragments like 03.05                                            
                                                                                                                                        
parser.py:355-372 + _AMOUNT_PATTERN — findall(...)[-1] returns dates as charges in column-aligned EOB layouts.                           
                                                                                                                                
M6. Prompt injection vector via OCR'd description fields                                                                                 
                                                                                                                                
ai_analysis.py:249-253 — adversarial text in item.description flows verbatim to Gemini/Claude. Small surface today (patient is the       
recipient + adversary), real surface for the planned B2B API path.                                                                       
                                                                                                                                
M7-M13: Type boundary issues (from agent #3)                                                                                             
                                                                                                                                
- 9 distinct shape clusters duplicated across 3+ representations (Pydantic + shared TS + inline TS).                                     
- 13 as casts in the frontend bypassing Zod (which is installed and never imported).           
- ProfileMember and InsurancePlan redeclared in snake_case in consumer components, shared types ignored.                                 
- Bill mapper duplicated character-for-character across analysis/route.ts and bills/[billId]/page.tsx.
- BQ writes lack num_dml_affected_rows verification — MERGE-affecting-zero-rows looks like success.                                      
- Pass 2 NPI strategy attribution is collected and discarded (no npi_match_strategy column in schema).                                   
- _extract_clean_api_key error message claims "expected exactly 39" when Google's key format isn't contractually fixed.          
                                                                                                                                        
---                                                                                                                              
📋 Regression-gate status (Option 1)                                                                                                     
                                                                                                                                        
┌───────────────┬────────┬────────────────────────────────────────┐                                                                      
│     Gate      │ Status │                 Notes                  │                                                                      
├───────────────┼────────┼────────────────────────────────────────┤                                                                      
│ Web typecheck        │ ✅     │ Clean                                  │                                                               
├──────────────────────┼────────┼────────────────────────────────────────┤                                                               
│ Web lint             │ ✅     │ Clean                                  │                                                               
├──────────────────────┼────────┼────────────────────────────────────────┤                                                               
│ Web tests            │ ❌     │ No test files exist; missing jsdom dep                           │                             
├──────────────────────┼────────┼──────────────────────────────────────────────────────────────────┤                                     
│ Web build            │ ✅     │ Clean                                                            │                                     
├──────────────────────┼────────┼──────────────────────────────────────────────────────────────────┤                       
│ Engine mypy --strict │ ✅     │ 22 files clean                                                   │                                     
├──────────────────────┼────────┼──────────────────────────────────────────────────────────────────┤                             
│ Engine ruff          │ ❌     │ 2 N806 errors                                                    │                                     
├──────────────────────┼────────┼──────────────────────────────────────────────────────────────────┤
│ Engine pytest        │ ❌     │ Collection fails — posthog missing in .venv, 421 tests never run │                                     
└──────────────────────┴────────┴──────────────────────────────────────────────────────────────────┘
                                                                                                                                        
---                                                                                            
Recommended order of work                                                                                                                
                                                                                                
1. Today (S1, S2, S3, S4, S5) — five stop-the-line bugs. S1 alone is one bill from production crash. Together: ~1 day.                   
2. This week (H1-H11) — billing math/parser bugs (H1-H3), pipeline cost/correctness (H4-H7), regression-gate fixes (H11+ M2), type
schema gaps (H8, H10). ~2-3 days.                                                                                                        
3. Next sprint (M-series) — frontend test coverage, Zod validation at boundaries (replaces all 13 as casts), de-duplicate
Bill/LineItem/ProfileMember mappers, prompt-injection mitigation. ~3-4 days.                                                             
                                                                                        
The single highest-leverage move is introducing Zod schemas in packages/shared/src/schemas/ and replacing every as X with  
XSchema.parse(...). That one change makes S1, H8, H10, M7-M13 either impossible or loud-failing. Sandra has Zod 3.23.8 installed already,
never imported.                                                                                                                         
                                                                                                                                        
⏺ Audit complete. 29 findings across the regression gate + 3 multi-agent reviews; 5 stop-the-line bugs, 11 high-severity, 13 medium. The   
headline is S1: a snake_case/camelCase mismatch on BillingError JSON keys that will crash the patient results page the first time the    
rules engine emits a real finding for a paying customer — your codebase is one well-formed bill from production crash. The 
Zod-replacement-of-as-casts move would prevent that whole class of bug; you already have the dependency installed and unused. 