-- Run in the Supabase SQL editor before enabling authenticated public access.
create table if not exists public.research_workspaces (
  user_id uuid primary key references auth.users(id) on delete cascade,
  object_key text not null,
  updated_at timestamptz not null default now()
);

alter table public.research_workspaces enable row level security;

create policy "users can read their workspace metadata"
on public.research_workspaces for select
to authenticated
using (auth.uid() = user_id);

insert into storage.buckets (id, name, public)
values ('research-workspaces', 'research-workspaces', false)
on conflict (id) do update set public = false;

-- Workspace archives are accessed only by the trusted FastAPI backend with the
-- service-role key. There is intentionally no client-side Storage policy.
