-- Row level security: authenticated users may only READ rows of their own college.
-- All writes go through the FastAPI backend using the service role (which bypasses RLS).

create or replace function public.current_college_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select college_id from profiles where id = (select auth.uid());
$$;
revoke execute on function public.current_college_id() from public, anon;
grant execute on function public.current_college_id() to authenticated;

alter table colleges      enable row level security;
alter table profiles      enable row level security;
alter table exams         enable row level security;
alter table questions     enable row level security;
alter table rubric_points enable row level security;
alter table scripts       enable row level security;
alter table script_pages  enable row level security;
alter table answers       enable row level security;
alter table final_marks   enable row level security;
alter table audit_log     enable row level security;
alter table ai_calls      enable row level security;

create policy colleges_read on colleges for select to authenticated
  using (id = (select public.current_college_id()));

create policy profiles_read on profiles for select to authenticated
  using (college_id = (select public.current_college_id()));

create policy exams_read on exams for select to authenticated
  using (college_id = (select public.current_college_id()));

create policy questions_read on questions for select to authenticated
  using (exists (select 1 from exams e where e.id = exam_id
                 and e.college_id = (select public.current_college_id())));

create policy rubric_points_read on rubric_points for select to authenticated
  using (exists (select 1 from questions q join exams e on e.id = q.exam_id
                 where q.id = question_id
                 and e.college_id = (select public.current_college_id())));

create policy scripts_read on scripts for select to authenticated
  using (exists (select 1 from exams e where e.id = exam_id
                 and e.college_id = (select public.current_college_id())));

create policy script_pages_read on script_pages for select to authenticated
  using (exists (select 1 from scripts s join exams e on e.id = s.exam_id
                 where s.id = script_id
                 and e.college_id = (select public.current_college_id())));

create policy answers_read on answers for select to authenticated
  using (exists (select 1 from scripts s join exams e on e.id = s.exam_id
                 where s.id = script_id
                 and e.college_id = (select public.current_college_id())));

create policy final_marks_read on final_marks for select to authenticated
  using (exists (select 1 from answers a join scripts s on s.id = a.script_id
                 join exams e on e.id = s.exam_id
                 where a.id = answer_id
                 and e.college_id = (select public.current_college_id())));

create policy audit_log_read on audit_log for select to authenticated
  using (college_id = (select public.current_college_id()));

-- ai_calls: no policies -> not readable by clients (backend only).
