-- Move the RLS helper out of the exposed `public` schema so it is not callable via /rest/v1/rpc.
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

create or replace function private.current_college_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select college_id from public.profiles where id = (select auth.uid());
$$;
revoke execute on function private.current_college_id() from public, anon;
grant execute on function private.current_college_id() to authenticated;

alter policy colleges_read on colleges using (id = (select private.current_college_id()));
alter policy profiles_read on profiles using (college_id = (select private.current_college_id()));
alter policy exams_read on exams using (college_id = (select private.current_college_id()));
alter policy questions_read on questions
  using (exists (select 1 from exams e where e.id = exam_id
                 and e.college_id = (select private.current_college_id())));
alter policy rubric_points_read on rubric_points
  using (exists (select 1 from questions q join exams e on e.id = q.exam_id
                 where q.id = question_id
                 and e.college_id = (select private.current_college_id())));
alter policy scripts_read on scripts
  using (exists (select 1 from exams e where e.id = exam_id
                 and e.college_id = (select private.current_college_id())));
alter policy script_pages_read on script_pages
  using (exists (select 1 from scripts s join exams e on e.id = s.exam_id
                 where s.id = script_id
                 and e.college_id = (select private.current_college_id())));
alter policy answers_read on answers
  using (exists (select 1 from scripts s join exams e on e.id = s.exam_id
                 where s.id = script_id
                 and e.college_id = (select private.current_college_id())));
alter policy final_marks_read on final_marks
  using (exists (select 1 from answers a join scripts s on s.id = a.script_id
                 join exams e on e.id = s.exam_id
                 where a.id = answer_id
                 and e.college_id = (select private.current_college_id())));
alter policy audit_log_read on audit_log using (college_id = (select private.current_college_id()));

drop function public.current_college_id();

-- Covering indexes for foreign keys.
create index audit_log_actor_idx on audit_log (actor_id);
create index exams_created_by_idx on exams (created_by);
create index final_marks_decided_by_idx on final_marks (decided_by);
create index scripts_uploaded_by_idx on scripts (uploaded_by);
