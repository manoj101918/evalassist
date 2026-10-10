import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { MyScript, QueueItem } from "../lib/types";
import { Button, Card, ErrorText, Spinner, StatusBadge } from "../components/ui";

function Progress({ s }: { s: MyScript }) {
  const total = s.answers.total ?? 0;
  const decided = s.answers.decided ?? 0;
  if (!total) return <span className="text-slate-400">–</span>;
  return (
    <div className="w-40">
      <div className="mb-0.5 flex justify-between text-xs text-slate-600">
        <span>{decided} / {total} answers</span>
        <span className="space-x-1">
          <span className="text-rose-700">{s.answers.red ?? 0}●</span>
          <span className="text-amber-600">{s.answers.yellow ?? 0}●</span>
          <span className="text-emerald-700">{s.answers.green ?? 0}●</span>
        </span>
      </div>
      <div className="h-1.5 rounded bg-slate-200">
        <div className="h-1.5 rounded bg-emerald-500" style={{ width: `${(100 * decided) / total}%` }} />
      </div>
    </div>
  );
}

export default function MyPapers() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [opening, setOpening] = useState<string | null>(null);
  const [openError, setOpenError] = useState<unknown>(null);
  const papers = useQuery({
    queryKey: ["my-scripts"],
    queryFn: () => api.get<MyScript[]>("/my/scripts"),
    refetchInterval: (q) =>
      q.state.data?.some((s) => s.status === "queued" || s.status === "processing") ? 10_000 : false,
  });

  const acceptGreen = useMutation({
    mutationFn: (scriptId: string) => api.send("POST", `/scripts/${scriptId}/accept-green`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-scripts"] }),
  });

  // Open the script's first unreviewed answer (or its first answer, to look over a finished one).
  const open = async (s: MyScript) => {
    setOpening(s.id);
    setOpenError(null);
    try {
      const pending = await api.get<QueueItem[]>(`/exams/${s.exam_id}/answers?script_id=${s.id}&status=pending`);
      const params = new URLSearchParams({ script_id: s.id });
      let first = pending[0];
      if (first) {
        params.set("status", "pending");
      } else {
        first = (await api.get<QueueItem[]>(`/exams/${s.exam_id}/answers?script_id=${s.id}`))[0];
      }
      if (first) navigate(`/exams/${s.exam_id}/review/${first.id}?${params.toString()}`);
    } catch (err) {
      setOpenError(err);
    } finally {
      setOpening(null);
    }
  };

  const rows = papers.data ?? [];
  const byExam = new Map<string, MyScript[]>();
  rows.forEach((s) => byExam.set(s.exam_id, [...(byExam.get(s.exam_id) ?? []), s]));
  const remaining = rows.filter((s) => s.status !== "reviewed").length;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold">My papers</h1>
        <p className="text-sm text-slate-600">
          Welcome, {me?.full_name}{me?.employee_id && ` (${me.employee_id})`}.{" "}
          {rows.length > 0 && `${remaining} of ${rows.length} assigned scripts still to evaluate.`}
        </p>
      </div>
      {papers.isLoading && <Spinner />}
      <ErrorText error={papers.error ?? openError ?? acceptGreen.error} />
      {papers.data && rows.length === 0 && (
        <Card><p className="text-sm text-slate-600">No scripts are assigned to you yet. Your exam coordinator will assign them.</p></Card>
      )}
      {[...byExam.values()].map((scripts) => (
        <Card key={scripts[0].exam_id} className="p-0">
          <div className="flex items-baseline justify-between border-b border-slate-100 px-4 py-2">
            <h2 className="font-medium">{scripts[0].exam.subject}</h2>
            <span className="text-sm text-slate-500">
              {scripts[0].exam.exam_date ?? ""} · {scripts[0].exam.total_marks} marks · {scripts.length} scripts
            </span>
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr><th className="px-4 py-2">Roll number</th><th>Pages</th><th>Status</th><th>Progress</th><th /></tr>
            </thead>
            <tbody>
              {scripts.map((s) => {
                const ready = s.status === "ready" || s.status === "reviewed";
                const started = (s.answers.decided ?? 0) > 0;
                return (
                  <tr key={s.id} className="border-t border-slate-100">
                    <td className="px-4 py-2 font-medium">{s.roll_number}</td>
                    <td>{s.page_count ?? "–"}</td>
                    <td><StatusBadge value={s.status} /></td>
                    <td><Progress s={s} /></td>
                    <td className="space-x-1 whitespace-nowrap pr-4 text-right">
                      {s.status === "ready" && (s.answers.green ?? 0) > 0 && (
                        <Button variant="secondary" disabled={acceptGreen.isPending}
                                title="Accept the AI's marks for every green answer in this script"
                                onClick={() => confirm(`Accept the AI's marks for the green answers of ${s.roll_number}?`)
                                  && acceptGreen.mutate(s.id)}>
                          Accept all green
                        </Button>
                      )}
                      {ready ? (
                        <Button variant={s.status === "reviewed" ? "secondary" : "primary"}
                                disabled={opening === s.id} onClick={() => open(s)}>
                          {s.status === "reviewed" ? "View marks" : started ? "Continue" : "Start evaluation"}
                        </Button>
                      ) : (
                        <span className="text-xs text-slate-500">
                          {s.status === "failed" ? "AI failed; ask your coordinator" : "AI is still reading this script"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      ))}
    </div>
  );
}
