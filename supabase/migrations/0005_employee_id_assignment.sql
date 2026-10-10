-- Teachers sign in with an employee ID, and scripts are assigned to a teacher for evaluation.
alter table profiles add column employee_id text;
create unique index profiles_employee_id_key on profiles (lower(employee_id)) where employee_id is not null;

alter table scripts add column assigned_to uuid references profiles (id) on delete set null;
alter table scripts add column assigned_at timestamptz;
create index scripts_assigned_to_idx on scripts (assigned_to);
