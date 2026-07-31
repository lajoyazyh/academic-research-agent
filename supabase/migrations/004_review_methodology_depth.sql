-- Reproducible search reporting, independent AI screening, evidence hierarchy,
-- quantitative context and claim-quality metadata.

alter table public.review_protocols
  add column if not exists methodology_schema_version integer not null default 1,
  add column if not exists legacy_incomplete_methodology boolean not null default true;

alter table public.review_search_queries
  add column if not exists original_query text,
  add column if not exists compiled_query text,
  add column if not exists field_scope jsonb not null default '[]'::jsonb,
  add column if not exists filters jsonb not null default '{}'::jsonb,
  add column if not exists execution_metadata jsonb not null default '{}'::jsonb,
  add column if not exists executed_at timestamptz,
  add column if not exists hit_count integer,
  add column if not exists attempt_count integer not null default 0;

alter table public.screening_decisions
  add column if not exists actor_type text not null default 'human',
  add column if not exists actor_id text,
  add column if not exists model_version text,
  add column if not exists blinded_to_peer boolean not null default false,
  add column if not exists supersedes_decision_id text;

alter table public.screening_decisions
  drop constraint if exists screening_decisions_actor_type_check;
alter table public.screening_decisions
  add constraint screening_decisions_actor_type_check
  check (actor_type in ('human', 'ai', 'adjudicator', 'migration'));

create index if not exists screening_decisions_resolution_idx
  on public.screening_decisions
  (user_id, session_id, protocol_id, candidate_id, stage, actor_type, created_at desc);

alter table public.evidence_extractions
  add column if not exists schema_version integer not null default 1,
  add column if not exists study_or_article_type text not null default 'unclear',
  add column if not exists evidence_level text not null default 'unclear',
  add column if not exists quantitative_results jsonb not null default '[]'::jsonb,
  add column if not exists technical_mechanism jsonb not null default '{}'::jsonb;

alter table public.study_appraisals
  add column if not exists schema_version integer not null default 1,
  add column if not exists completeness jsonb not null default '{}'::jsonb;

alter table public.review_claims
  add column if not exists claim_type text not null default 'unclassified',
  add column if not exists evidence_level text not null default 'unverified',
  add column if not exists evidence_fit boolean not null default false,
  add column if not exists numeric_context_complete boolean not null default false,
  add column if not exists normative_strength_ok boolean not null default false;

comment on column public.review_search_queries.compiled_query is
  'Exact source-specific query sent to the bibliographic service.';
comment on column public.screening_decisions.blinded_to_peer is
  'True when the reviewer could not see another reviewer decision before voting.';
comment on column public.evidence_extractions.quantitative_results is
  'Structured result context including dataset, model, baseline, metric, effect type and evidence location.';
