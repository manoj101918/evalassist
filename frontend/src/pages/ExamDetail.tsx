import { useRef, useState, type DragEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { isStaff, useAuth } from "../lib/auth";
import type { ExamDetail as Exam, Script, UserRow } from "../lib/types";
import QuestionEditor from "../components/QuestionEditor";
import { Button, Card, ErrorText, Spinner, StatusBadge } from "../components/ui";

interface UploadResult { filename: string; ok: boolean; error?: string }

function Questions({ exam }: { exam: Exam }) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<string | "new" | null>(null);
  const remove = useMutation({
    mutationFn: (id: string) => api.send("DELETE", `/questions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exam", exam.id] }),
  });
  const nextPosition = exam.questions.reduce((m, q) => Math.max(m, q.position + 1), 0);

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-medium">Questions & rubrics</h2>
        {editing === null && <Button variant="secondary" onClick={() => setEditing("new")}>+ Add question</Button>}
      </div>
      {exam.rubric_problems.length > 0 && (
        <ul className="mb-3 list-disc rounded-md bg-amber-50 py-2 pl-8 pr-3 text-sm text-amber-800">
          {exam.rubric_problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}
      <div className="space-y-2">
        {exam.questions.map((q) =>
          editing === q.id ? (
            <QuestionEditor key={q.id} examId={exam.id} question={q} nextPosition={nextPosition}
                            onDone={() => setEditing(null)} />
          ) : (
            <div key={q.id} className="rounded-md border border-slate-200 p-3">
              <div className="flex items-start gap-3">
                <span className="font-semibold">Q{q.label}</span>
                <p className="flex-1 text-sm">{q.text}</p>
                <span className="text-sm text-slate-600">{q.max_marks} marks</span>
                <Button variant="ghost" onClick={() => setEditing(q.id)}>Edit</Button>
                <Button variant="ghost" onClick={() => confirm(`Delete question ${q.label}?`) && remove.mutate(q.id)}>
                  Delete
                </Button>
              </div>
              {q.qtype === "mcq" ? (
                <p className="mt-1 pl-8 text-sm text-slate-600">
                  Multiple choice · correct answer <span className="font-semibold">{q.correct_option}</span>
                  <span className="text-slate-400"> · graded by rule, no AI</span>
                </p>
              ) : (
                <ul className="mt-2 space-y-0.5 pl-8 text-sm text-slate-600">
                  {q.rubric_points.map((p) => (
                    <li key={p.id}>• {p.description} <span className="text-slate-400">({p.marks})</span></li>
                  ))}
                </ul>
              )}
            </div>
          ),
        )}
        {editing === "new" && (
          <QuestionEditor examId={exam.id} nextPosition={nextPosition} onDone={() => setEditing(null)} />
        )}
        {exam.questions.length === 0 && editing === null && (
          <p className="text-sm text-slate-600">Add each question with its marking points before uploading scripts.</p>
        )}
      </div>
    </Card>
  );
}

function Upload({ examId }: { examId: string }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [results, setResults] = useState<UploadResult[]>([]);
  const upload = useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f));
      return api.upload<UploadResult[]>(`/exams/${examId}/scripts`, form);
    },
    onSuccess: (r) => {
      setResults(r);
      qc.invalidateQueries({ queryKey: ["scripts", examId] });
    },
  });
  const start = (list: FileList | null) => {
    const files = Array.from(list ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (files.length) upload.mutate(files);
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    start(e.dataTransfer.files);
  };

  return (
    <Card>
      <h2 className="mb-2 font-medium">Upload scanned scripts</h2>
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => input.current?.click()}
        className={`cursor-pointer rounded-md border-2 border-dashed p-6 text-center text-sm ${
          dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 text-slate-600"}`}
      >
        {upload.isPending ? "Uploading…" : "Drop PDF booklets here, or click to choose. Name each file by roll number, e.g. 21CS045.pdf"}
        <input ref={input} type="file" accept="application/pdf" multiple hidden
               onChange={(e) => { start(e.target.files); e.target.value = ""; }} />
      </div>
      <ErrorText error={upload.error} />
      {results.length > 0 && (
        <ul className="mt-2 text-sm">
          {results.map((r) => (
            <li key={r.filename} className={r.ok ? "text-emerald-700" : "text-rose-700"}>
              {r.ok ? "✓" : "✕"} {r.filename}{r.error && `: ${r.error}`}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Scripts({ examId, staff }: { examId: string; staff: boolean }) {
  const qc = useQueryClient();
  const scripts = useQuery({
    queryKey: ["scripts", examId],
    queryFn: () => api.get<Script[]>(`/exams/${examId}/scripts`),
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.status === "queued" || s.status === "processing") ? 5000 : false,
  });
  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "retry" | "delete" }) =>
      kind === "delete" ? api.send("DELETE", `/scripts/${id}`) : api.send("POST", `/scripts/${id}/retry`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["scripts", examId] });
      qc.invalidateQueries({ queryKey: ["queue", examId] });
    },
  });
  const teachers = useQuery({
    queryKey: ["users", "teacher"],
    queryFn: () => api.get<UserRow[]>("/users?role=teacher"),
    enabled: staff,
  });
  const assign = useMutation({
    mutationFn: (body: { script_ids: string[]; teacher_id: string | null }) =>
      api.send("POST", `/exams/${examId}/assign`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scripts", examId] }),
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkTeacher, setBulkTeacher] = useState("");
  const [showDistribute, setShowDistribute] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const distribute = useMutation({
    mutationFn: (teacher_ids: string[]) =>
      api.send<{ assigned: number }>("POST", `/exams/${examId}/assign/distribute`, { teacher_ids, only_unassigned: true }),
    onSuccess: () => {
      setShowDistribute(false);
      setChosen(new Set());
      qc.invalidateQueries({ queryKey: ["scripts", examId] });
    },
  });
  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  };
  const assignSelected = () =>
    assign.mutate({ script_ids: [...selected], teacher_id: bulkTeacher || null },
                  { onSuccess: () => { setSelected(new Set()); setBulkTeacher(""); } });

  if (scripts.isLoading) return <Spinner />;
  const rows = scripts.data ?? [];
  const unassigned = rows.filter((s) => !s.assigned_to).length;
  const teacherList = teachers.data ?? [];
  const workload = teacherList
    .map((t) => {
      const mine = rows.filter((s) => s.assigned_to === t.id);
      return { t, total: mine.length, done: mine.filter((s) => s.status === "reviewed").length };
    })
    .filter((w) => w.total > 0);
  const allSelected = rows.length > 0 && selected.size === rows.length;
  return (
    <Card>
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h2 className="font-medium">Scripts ({rows.length})</h2>
        {staff && rows.length > 0 && (
          <span className={`text-sm ${unassigned ? "text-amber-700" : "text-emerald-700"}`}>
            {unassigned ? `${unassigned} not assigned to a teacher` : "All scripts assigned"}
          </span>
        )}
        {staff && unassigned > 0 && teacherList.length > 0 && (
          <Button variant="secondary" className="ml-auto" onClick={() => setShowDistribute(!showDistribute)}>
            Distribute unassigned…
          </Button>
        )}
        {staff && teachers.data && teacherList.length === 0 && (
          <span className="ml-auto text-sm text-amber-700">Add teachers on the Users page to assign scripts.</span>
        )}
      </div>

      {staff && showDistribute && (
        <div className="mb-3 rounded-md border border-indigo-200 bg-indigo-50/40 p-3 text-sm">
          <p className="mb-2 font-medium">Which teachers evaluate this exam?</p>
          <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
            {teacherList.map((t) => (
              <label key={t.id} className="flex items-center gap-1">
                <input type="checkbox" checked={chosen.has(t.id)} onChange={() => setChosen(toggle(chosen, t.id))} />
                {t.full_name}{t.employee_id && <span className="text-slate-500">({t.employee_id})</span>}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={chosen.size === 0 || distribute.isPending} onClick={() => distribute.mutate([...chosen])}>
              Share {unassigned} scripts among {chosen.size || "…"} teacher{chosen.size === 1 ? "" : "s"}
            </Button>
            <Button variant="ghost" onClick={() => setShowDistribute(false)}>Cancel</Button>
            <span className="text-slate-500">Each teacher gets a similar number, counting scripts they already have.</span>
          </div>
        </div>
      )}

      {staff && selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-md bg-slate-100 p-2 text-sm">
          <span className="font-medium">{selected.size} selected</span>
          <span>Assign to</span>
          <select className="rounded border border-slate-300 bg-white px-1 py-0.5" value={bulkTeacher}
                  onChange={(e) => setBulkTeacher(e.target.value)}>
            <option value="">— Not assigned —</option>
            {teacherList.map((t) => (
              <option key={t.id} value={t.id}>{t.full_name}{t.employee_id && ` (${t.employee_id})`}</option>
            ))}
          </select>
          <Button disabled={assign.isPending} onClick={assignSelected}>Apply</Button>
          <Button variant="ghost" onClick={() => setSelected(new Set())}>Clear selection</Button>
        </div>
      )}

      {staff && workload.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2 text-xs">
          {workload.map(({ t, total, done }) => (
            <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5">
              {t.full_name}: {done}/{total} evaluated
            </span>
          ))}
        </div>
      )}
      <ErrorText error={scripts.error ?? action.error ?? assign.error ?? distribute.error} />
      {rows.length === 0 ? (
        <p className="text-sm text-slate-600">No scripts uploaded yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr>
                {staff && (
                  <th className="w-6 py-1">
                    <input type="checkbox" aria-label="Select all" checked={allSelected}
                           onChange={() => setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)))} />
                  </th>
                )}
                <th className="py-1">Roll number</th><th>Pages</th><th>Status</th>
                <th>Assigned to</th><th>AI confidence</th><th>Reviewed</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className={`border-t border-slate-100 ${selected.has(s.id) ? "bg-indigo-50/50" : ""}`}>
                  {staff && (
                    <td>
                      <input type="checkbox" aria-label={`Select ${s.roll_number}`} checked={selected.has(s.id)}
                             onChange={() => setSelected(toggle(selected, s.id))} />
                    </td>
                  )}
                  <td className="py-1.5 font-medium">{s.roll_number}</td>
                  <td>{s.page_count ?? "–"}</td>
                  <td>
                    <StatusBadge value={s.status} />
                    {s.error && <p className="max-w-xs truncate text-xs text-rose-700" title={s.error}>{s.error}</p>}
                  </td>
                  <td>
                    {staff ? (
                      <select className="rounded border border-slate-300 bg-white px-1 py-0.5 text-sm"
                              value={s.assigned_to ?? ""} disabled={assign.isPending}
                              onChange={(e) => assign.mutate({ script_ids: [s.id], teacher_id: e.target.value || null })}>
                        <option value="">— Not assigned —</option>
                        {teacherList.map((t) => (
                          <option key={t.id} value={t.id}>{t.full_name}{t.employee_id && ` (${t.employee_id})`}</option>
                        ))}
                      </select>
                    ) : (
                      s.assignee?.full_name ?? "–"
                    )}
                  </td>
                  <td className="space-x-2">
                    {s.answers.total ? (
                      <>
                        <span className="text-emerald-700">{s.answers.green ?? 0}●</span>
                        <span className="text-amber-600">{s.answers.yellow ?? 0}●</span>
                        <span className="text-rose-700">{s.answers.red ?? 0}●</span>
                      </>
                    ) : "–"}
                  </td>
                  <td>{s.answers.total ? `${s.answers.decided ?? 0}/${s.answers.total}` : "–"}</td>
                  <td className="space-x-1 text-right">
                    {staff && s.status === "failed" && (
                      <Button variant="secondary" onClick={() => action.mutate({ id: s.id, kind: "retry" })}>Retry</Button>
                    )}
                    {staff && (
                      <Button variant="ghost" onClick={() =>
                        confirm(`Delete script ${s.roll_number} and all its marks?`) && action.mutate({ id: s.id, kind: "delete" })}>
                        Delete
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function QuestionPaperUpload({ examId }: { examId: string }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload(`/exams/${examId}/question-paper`, form);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["exam", examId] }),
  });
  return (
    <>
      <Button variant="ghost" onClick={() => input.current?.click()} disabled={upload.isPending}
              title={upload.error instanceof Error ? upload.error.message : undefined}>
        {upload.isPending ? "Uploading…" : upload.isError ? "Upload failed, retry" : "Upload question paper"}
      </Button>
      <input ref={input} type="file" accept="application/pdf" hidden
             onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
    </>
  );
}

export default function ExamDetail() {
  const { examId = "" } = useParams();
  const { me } = useAuth();
  const staff = isStaff(me);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const exam = useQuery({ queryKey: ["exam", examId], queryFn: () => api.get<Exam>(`/exams/${examId}`) });

  if (exam.isLoading) return <Spinner />;
  if (!exam.data) return <ErrorText error={exam.error} />;
  const e = exam.data;

  const doExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await api.download(`/exams/${examId}/export.xlsx`, "marks.xlsx");
    } catch (err) {
      setExportError(err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/" className="text-sm text-slate-500 hover:underline">← Exams</Link>
        <h1 className="text-xl font-semibold">{e.subject}</h1>
        <span className="text-sm text-slate-500">{e.exam_date} · {e.total_marks} marks</span>
        {e.question_paper_url && (
          <a href={e.question_paper_url} target="_blank" rel="noreferrer" className="text-sm text-indigo-700 hover:underline">
            Question paper
          </a>
        )}
        {staff && <QuestionPaperUpload examId={examId} />}
        <div className="ml-auto flex gap-2">
          <Link to={`/exams/${examId}/review`}><Button>Review answers</Button></Link>
          {staff && <Button variant="secondary" onClick={doExport} disabled={exporting}>
            {exporting ? "Exporting…" : "Export to Excel"}
          </Button>}
        </div>
      </div>
      <ErrorText error={exportError} />
      <Questions exam={e} />
      {staff && <Upload examId={examId} />}
      <Scripts examId={examId} staff={staff} />
    </div>
  );
}
