-- Question types: MCQs are graded by exact rules (no AI call); short/long answers by the AI.
alter table questions add column qtype text not null default 'short'
  check (qtype in ('short', 'long', 'mcq'));
alter table questions add column correct_option text
  check (correct_option is null or correct_option ~ '^[A-Z]$');
alter table questions add constraint questions_mcq_has_option
  check (qtype <> 'mcq' or correct_option is not null);
