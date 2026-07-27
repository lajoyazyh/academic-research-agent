-- Queryable research workspace model.
--
-- The previous release stored one workspace.zip per user. These tables turn
-- session lists and session state into normal Postgres reads while Storage is
-- reserved for large paper files and compatibility archives.

create table if not exists public.research_sessions (
  user_id uuid not null references auth.users(id) on delete cascade,
  session_id text not null,
  topic text not null default '',
  state text not null default 'planning',
  state_label text not null default '',
  created_at timestamptz,
  updated_at timestamptz not null default now(),
  paper_count integer not null default 0 check (paper_count >= 0),
  note_size integer not null default 0 check (note_size >= 0),
  total_notes integer not null default 0 check (total_notes >= 0),
  review_count integer not null default 0 check (review_count >= 0),
  review_version integer not null default 0 check (review_version >= 0),
  snapshot jsonb not null default '{}'::jsonb,
  primary key (user_id, session_id)
);

create index if not exists research_sessions_user_updated_idx
  on public.research_sessions (user_id, updated_at desc);

create table if not exists public.research_papers (
  user_id uuid not null,
  session_id text not null,
  paper_id text not null,
  title text not null default '',
  status text not null default 'pending',
  source_type text not null default '',
  published_year integer,
  authors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, paper_id),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create index if not exists research_papers_session_status_idx
  on public.research_papers (user_id, session_id, status);

create table if not exists public.research_artifacts (
  user_id uuid not null,
  session_id text not null,
  kind text not null,
  version integer not null default 0,
  content_text text,
  content_json jsonb,
  object_key text,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, kind, version),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create table if not exists public.research_conversations (
  user_id uuid not null,
  session_id text not null,
  conversation_id text not null,
  title text not null default '',
  message_count integer not null default 0 check (message_count >= 0),
  created_at timestamptz,
  updated_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  primary key (user_id, session_id, conversation_id),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create table if not exists public.research_messages (
  user_id uuid not null,
  session_id text not null,
  conversation_id text not null,
  message_index integer not null,
  role text not null default '',
  content text not null default '',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz,
  primary key (user_id, session_id, conversation_id, message_index),
  foreign key (user_id, session_id, conversation_id)
    references public.research_conversations(user_id, session_id, conversation_id)
    on delete cascade
);

create table if not exists public.research_runs (
  user_id uuid not null,
  session_id text not null,
  run_id text not null,
  kind text not null default '',
  status text not null default '',
  phase text not null default '',
  checkpoint text not null default '',
  retryable boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  progress jsonb not null default '{}'::jsonb,
  message text not null default '',
  error_code text,
  created_at timestamptz,
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, run_id),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create index if not exists research_runs_session_updated_idx
  on public.research_runs (user_id, session_id, updated_at desc);

create table if not exists public.research_files (
  user_id uuid not null,
  session_id text not null,
  relative_path text not null,
  object_key text not null,
  content_type text not null default 'application/octet-stream',
  byte_size bigint not null default 0 check (byte_size >= 0),
  sha256 text not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, session_id, relative_path),
  foreign key (user_id, session_id)
    references public.research_sessions(user_id, session_id) on delete cascade
);

create index if not exists research_files_session_idx
  on public.research_files (user_id, session_id);

alter table public.research_sessions enable row level security;
alter table public.research_papers enable row level security;
alter table public.research_artifacts enable row level security;
alter table public.research_conversations enable row level security;
alter table public.research_messages enable row level security;
alter table public.research_runs enable row level security;
alter table public.research_files enable row level security;

grant select on public.research_sessions to authenticated;
grant select on public.research_papers to authenticated;
grant select on public.research_artifacts to authenticated;
grant select on public.research_conversations to authenticated;
grant select on public.research_messages to authenticated;
grant select on public.research_runs to authenticated;
grant select on public.research_files to authenticated;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'research_sessions',
    'research_papers',
    'research_artifacts',
    'research_conversations',
    'research_messages',
    'research_runs',
    'research_files'
  ]
  loop
    execute format('drop policy if exists "users can read own %s" on public.%I', table_name, table_name);
    execute format(
      'create policy "users can read own %s" on public.%I for select to authenticated using (auth.uid() = user_id)',
      table_name,
      table_name
    );
  end loop;
end
$$;

comment on table public.research_sessions is
  'Queryable session state. snapshot excludes credentials and binary paper files.';
comment on table public.research_files is
  'Metadata for per-file objects stored in the private research-workspaces bucket.';
