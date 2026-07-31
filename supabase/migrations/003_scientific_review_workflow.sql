-- Protocol-driven scientific review workflow.
-- Large/full-text files remain in private Storage. These relations contain
-- metadata and auditable decisions only; API keys and raw credentials are
-- never persisted.

create table if not exists public.review_protocols (
  user_id uuid not null,
  session_id text not null,
  protocol_id text not null,
  version integer not null check (version > 0),
  status text not null check (status in ('draft', 'confirmed', 'superseded')),
  mode text not null check (mode in ('rapid', 'systematic', 'scoping', 'technical')),
  research_question text not null default '',
  candidate_cap integer not null check (candidate_cap between 30 and 2000),
  protocol jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, protocol_id),
  unique (user_id, session_id, version),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create table if not exists public.research_candidates (
  user_id uuid not null,
  session_id text not null,
  candidate_id text not null,
  protocol_id text not null,
  paper_id text not null,
  status text not null default 'candidate',
  screening_stage text not null default 'discovered',
  record jsonb not null default '{}'::jsonb,
  discovered_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, candidate_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

create table if not exists public.review_search_queries (
  user_id uuid not null,
  session_id text not null,
  search_query_id text not null,
  protocol_id text not null,
  source text not null,
  query_text text not null,
  status text not null default 'pending',
  query_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  completed_at timestamptz,
  primary key (user_id, session_id, search_query_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

create index if not exists research_candidates_screening_idx
  on public.research_candidates (user_id, session_id, protocol_id, screening_stage, status);

create table if not exists public.screening_decisions (
  user_id uuid not null,
  session_id text not null,
  decision_id text not null,
  protocol_id text not null,
  candidate_id text not null,
  paper_id text not null,
  stage text not null check (stage in ('title_abstract', 'full_text')),
  decision text not null check (decision in ('include', 'exclude', 'uncertain')),
  reason_code text,
  reviewer text not null default 'human',
  decision_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, session_id, decision_id),
  foreign key (user_id, session_id, candidate_id)
    references public.research_candidates(user_id, session_id, candidate_id) on delete cascade
);

create table if not exists public.evidence_extractions (
  user_id uuid not null,
  session_id text not null,
  extraction_id text not null,
  protocol_id text not null,
  paper_id text not null,
  evidence_basis text not null default 'unknown',
  review_status text not null default 'ai_draft',
  extraction jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, extraction_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

create table if not exists public.study_appraisals (
  user_id uuid not null,
  session_id text not null,
  appraisal_id text not null,
  protocol_id text not null,
  paper_id text not null,
  profile text not null default 'general',
  overall_judgement text not null default 'unclear',
  appraisal jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, session_id, appraisal_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

create table if not exists public.inclusion_snapshots (
  user_id uuid not null,
  session_id text not null,
  snapshot_id text not null,
  protocol_id text not null,
  version integer not null check (version > 0),
  paper_ids jsonb not null default '[]'::jsonb,
  confirmed_by text not null default 'human',
  confirmed_at timestamptz not null default now(),
  primary key (user_id, session_id, snapshot_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

create table if not exists public.synthesis_groups (
  user_id uuid not null,
  session_id text not null,
  synthesis_group_id text not null,
  protocol_id text not null,
  inclusion_snapshot_id text not null,
  synthesis_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, session_id, synthesis_group_id),
  foreign key (user_id, session_id, inclusion_snapshot_id)
    references public.inclusion_snapshots(user_id, session_id, snapshot_id) on delete cascade
);

create table if not exists public.review_claims (
  user_id uuid not null,
  session_id text not null,
  claim_id text not null,
  protocol_id text not null,
  inclusion_snapshot_id text not null,
  claim_text text not null default '',
  support_status text not null default 'unverified',
  claim_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, session_id, claim_id),
  foreign key (user_id, session_id, inclusion_snapshot_id)
    references public.inclusion_snapshots(user_id, session_id, snapshot_id) on delete cascade
);

create table if not exists public.review_versions (
  user_id uuid not null,
  session_id text not null,
  review_version_id text not null,
  protocol_id text not null,
  inclusion_snapshot_id text,
  version integer not null check (version > 0),
  output_label text not null default 'incomplete_research_draft',
  version_data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, session_id, review_version_id),
  foreign key (user_id, session_id, protocol_id)
    references public.review_protocols(user_id, session_id, protocol_id) on delete cascade
);

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'review_protocols',
    'review_search_queries',
    'research_candidates',
    'screening_decisions',
    'evidence_extractions',
    'study_appraisals',
    'inclusion_snapshots',
    'synthesis_groups',
    'review_claims',
    'review_versions'
  ]
  loop
    execute format('alter table public.%I enable row level security', table_name);
    execute format('grant select on public.%I to authenticated', table_name);
    execute format('drop policy if exists "users can read own %s" on public.%I', table_name, table_name);
    execute format(
      'create policy "users can read own %s" on public.%I for select to authenticated using (auth.uid() = user_id)',
      table_name,
      table_name
    );
  end loop;
end
$$;

comment on table public.review_protocols is
  'Versioned review protocols. A confirmed protocol is required before discovery.';
comment on table public.screening_decisions is
  'Criterion-level title/abstract and full-text decisions with auditable reasons.';
comment on table public.review_claims is
  'Claim-to-evidence audit records; no API keys or private credentials are allowed.';
