import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { isStaff, useAuth } from "../lib/auth";
import type { Exam } from "../lib/types";
import { Button, Card, ErrorText, Spinner, inputClass } from "../components/ui";

function NewExamForm({ onCancel }: { onCancel: () => void }) {
  const navigate = useNavigate();
  const [subject, setSubject] = useState("");
  const [examDate, setExamDate] = useState("");
  const [totalMarks, setTotalMarks] = useState("");
  const create = useMutation({
    mutationFn: () =>
      api.send<Exam>("POST", "/exams", {
        subject, exam_date: examDate || null, total_marks: Number(totalMarks),
      }),
    onSuccess: (exam) => navigate(`/exams/${exam.id}`),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  return (
    <Card className="mb-6">
      <form onSubmit={submit} className="grid grid-cols-1 gap-3 sm:grid-cols-4 sm:items-end">
        <label className="text-sm sm:col-span-2">
          Subject
          <input className={inputClass} required value={subject} onChange={(e) => setSubject(e.target.value)}
                 placeholder="e.g. Data Structures – Internal 1" autoFocus />
        </label>
        <label className="text-sm">
          Exam date
          <input className={inputClass} type="date" value={examDate} onChange={(e) => setExamDate(e.target.value)} />
        </label>
        <label className="text-sm">
          Total marks
          <input className={inputClass} type="number" min="1" step="0.5" required value={totalMarks}
                 onChange={(e) => setTotalMarks(e.target.value)} />
        </label>
        <div className="flex gap-2 sm:col-span-4">
          <Button type="submit" disabled={create.isPending}>Create exam</Button>
          <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
          <ErrorText error={create.error} />
        </div>
      </form>
    </Card>
  );
}

export default function Exams() {
  const { me } = useAuth();
  const [creating, setCreating] = useState(false);
  const exams = useQuery({ queryKey: ["exams"], queryFn: () => api.get<Exam[]>("/exams") });

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Exams</h1>
        {isStaff(me) && !creating && <Button onClick={() => setCreating(true)}>New exam</Button>}
      </div>
      {creating && <NewExamForm onCancel={() => setCreating(false)} />}
      {exams.isLoading && <Spinner />}
      <ErrorText error={exams.error} />
      {exams.data?.length === 0 && (
        <Card><p className="text-sm text-slate-600">No exams yet.{isStaff(me) && " Create one to get started."}</p></Card>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        {exams.data?.map((e) => {
          const c = e.script_counts ?? {};
          const total = Object.values(c).reduce((a, b) => a + (b ?? 0), 0);
          return (
            <Link key={e.id} to={`/exams/${e.id}`}>
              <Card className="transition hover:border-indigo-300">
                <div className="flex items-baseline justify-between">
                  <h2 className="font-medium">{e.subject}</h2>
                  <span className="text-sm text-slate-500">{e.exam_date ?? ""}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">
                  {e.total_marks} marks · {total} scripts
                  {total > 0 && ` · ${c.reviewed ?? 0} reviewed · ${c.ready ?? 0} to review`}
                  {(c.queued ?? 0) + (c.processing ?? 0) > 0 && ` · ${(c.queued ?? 0) + (c.processing ?? 0)} with AI`}
                  {(c.failed ?? 0) > 0 && <span className="text-rose-700"> · {c.failed} failed</span>}
                </p>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
