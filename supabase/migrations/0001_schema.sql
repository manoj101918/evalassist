-- EvalAssist core schema

create type user_role as enum ('admin', 'coordinator', 'teacher');
create type script_status as enum ('uploaded', 'queued', 'processing', 'ready', 'reviewed', 'failed');
create type legibility as enum ('clear', 'partial', 'unreadable');
create type confidence_level as enum ('green', 'yellow', 'red');
create type answer_status as enum ('pending', 'accepted', 'changed');

create table colleges (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan text not null default 'pilot',
  contact_email text,
  created_at timestamptz not null default now()
);

create table profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  college_id uuid not null references colleges (id) on delete cascade,
  full_name text not null,
  email text not null,
  role user_role not null default 'teacher',
  created_at timestamptz not null default now()
);
create index profiles_college_idx on profiles (college_id);

create table exams (
  id uuid primary key default gen_random_uuid(),
  college_id uuid not null references colleges (id) on delete cascade,
  subject text not null,
  exam_date date,
  total_marks numeric(6, 2) not null check (total_marks > 0),
  question_paper_path text,
  created_by uuid references profiles (id) on delete set null,
  created_at timestamptz not null default now()
);
create index exams_college_idx on exams (college_id);

create table questions (
  id uuid primary key default gen_random_uuid(),
  exam_id uuid not null references exams (id) on delete cascade,
  label text not null,
  text text not null,
  max_marks numeric(6, 2) not null check (max_marks > 0),
  position int not null default 0,
  model_answer text,
  created_at timestamptz not null default now(),
  unique (exam_id, label)
);
create index questions_exam_idx on questions (exam_id);

create table rubric_points (
  id uuid primary key default gen_random_uuid(),
  question_id uuid not null references questions (id) on delete cascade,
  description text not null,
  marks numeric(6, 2) not null check (marks > 0),
  position int not null default 0
);
create index rubric_points_question_idx on rubric_points (question_id);

create table scripts (
  id uuid primary key default gen_random_uuid(),
  exam_id uuid not null references exams (id) on delete cascade,
  roll_number text not null,
  pdf_path text not null,
  page_count int,
  status script_status not null default 'uploaded',
  error text,
  attempts int not null default 0,
  uploaded_by uuid references profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  processed_at timestamptz,
  unique (exam_id, roll_number)
);
create index scripts_exam_idx on scripts (exam_id);
create index scripts_status_idx on scripts (status);

create table script_pages (
  id uuid primary key default gen_random_uuid(),
  script_id uuid not null references scripts (id) on delete cascade,
  page_no int not null,
  image_path text not null,
  transcription text,
  legibility legibility,
  has_diagram_or_math boolean not null default false,
  unique (script_id, page_no)
);

create table answers (
  id uuid primary key default gen_random_uuid(),
  script_id uuid not null references scripts (id) on delete cascade,
  question_id uuid not null references questions (id) on delete cascade,
  page_numbers int[] not null default '{}',
  transcription text not null default '',
  ai_marks numeric(6, 2),
  ai_breakdown jsonb not null default '[]',
  ai_reason text,
  check_marks numeric(6, 2),
  check_breakdown jsonb not null default '[]',
  confidence confidence_level not null default 'red',
  confidence_reasons text[] not null default '{}',
  status answer_status not null default 'pending',
  created_at timestamptz not null default now(),
  unique (script_id, question_id)
);
create index answers_question_idx on answers (question_id);

create table final_marks (
  answer_id uuid primary key references answers (id) on delete cascade,
  marks numeric(6, 2) not null check (marks >= 0),
  decided_by uuid references profiles (id) on delete set null,
  decided_at timestamptz not null default now(),
  comment text
);

create table audit_log (
  id bigint generated always as identity primary key,
  college_id uuid not null references colleges (id) on delete cascade,
  actor_id uuid references profiles (id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);
create index audit_log_entity_idx on audit_log (entity_type, entity_id);
create index audit_log_college_idx on audit_log (college_id, created_at desc);

create table ai_calls (
  id bigint generated always as identity primary key,
  script_id uuid references scripts (id) on delete cascade,
  step text not null,
  model text not null,
  input_tokens int not null default 0,
  output_tokens int not null default 0,
  cache_read_tokens int not null default 0,
  cache_write_tokens int not null default 0,
  cost_usd numeric(10, 6) not null default 0,
  created_at timestamptz not null default now()
);
create index ai_calls_script_idx on ai_calls (script_id);

-- Atomically claim the next queued script for the worker.
create or replace function claim_next_script()
returns setof scripts
language sql
security definer
set search_path = public
as $$
  update scripts
     set status = 'processing', attempts = attempts + 1, error = null
   where id = (
     select id from scripts
      where status = 'queued'
      order by created_at
      limit 1
      for update skip locked
   )
  returning *;
$$;
revoke execute on function claim_next_script() from public, anon, authenticated;
