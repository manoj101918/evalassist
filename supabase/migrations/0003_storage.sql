-- Private bucket for scanned scripts, rendered page images and question papers.
-- No storage policies: only the backend (service role) reads/writes; the UI gets signed URLs.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('scripts', 'scripts', false, 52428800, array['application/pdf', 'image/png'])
on conflict (id) do nothing;
