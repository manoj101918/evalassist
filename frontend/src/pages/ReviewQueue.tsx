import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { isStaff, useAuth } from "../lib/auth";
import type { ExamDetail, QueueItem } from "../lib/types";
import { Card, ConfidenceBadge, ErrorText, Spinner, inputClass } from "../components/ui";

export function queuePath(examId: string, params: URLSearchParams): string {
  const q = new URLSearchParams();
  for (const k of ["confidence", "status", "question_id", "script_id"]) {
    const v = params.get(k);
    if (v) q.set(k, v);
  }
  const s = q.toString();
  return `/exams/${examId}/answers${s ? `?${s}` : ""}`;
}

export function useQueue(examId: string, params: URLSearchParams) {
  const path = queuePath(examId, params);
  return useQuery({ queryKey: ["queue", examId, path], queryFn: () => api.get<QueueItem[]>(path) });
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
            className={`rounded-full px-3 py-1 text-sm ring-1 ${active ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-700 ring-slate-300 hover:bg-slate-50"}`}>
      {children}
    </button>
  );
}

export default function ReviewQueue() {
  const { examId = "" } = useParams();
  const [params, setParams] = useSearchParams({ status: "pending" });
  const navigate = useNavigate();
  const { me } = useAuth();
  const exam = useQuery({ queryKey: ["exam", examId], queryFn: () => api.get<ExamDetail>(`/exams/${examId}`) });
  const queue = useQueue(examId, params);
  const all = useQuery({
    queryKey: ["queue", examId, "all"],
    queryFn: () => api.get<QueueItem[]>(`/exams/${examId}/answers`),
  });

  const set = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next, { replace: true });
  };

  const total = all.data?.length ?? 0;
  const decided = all.data?.filter((a) => a.status !== "pending").length ?? 0;
  const counts = { green: 0, yellow: 0, red: 0 };
  all.data?.forEach((a) => { if (a.status === "pending") counts[a.confidence] += 1; });
  const confidence = params.get("confidence");
  const status = params.get("status");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={isStaff(me) ? `/exams/${examId}` : "/"} className="text-sm text-slate-500 hover:underline">
          ← {isStaff(me) ? exam.data?.subject ?? "Exam" : "My papers"}
        </Link>
        <h1 className="text-xl font-semibold">Review answers</h1>
        <div className="ml-auto w-64">
          <div className="mb-1 text-right text-sm text-slate-600">{decided} / {total} answers decided</div>
          <div className="h-2 rounded bg-slate-200">
            <div className="h-2 rounded bg-emerald-500" style={{ width: `${total ? (100 * decided) / total : 0}%` }} />
          </div>
        </div>
      </div>

      <Card className="flex flex-wrap items-center gap-2">
        <Chip active={!confidence} onClick={() => set("confidence", null)}>All colours</Chip>
        <Chip active={confidence === "red"} onClick={() => set("confidence", "red")}>Red ({counts.red})</Chip>
        <Chip active={confidence === "yellow"} onClick={() => set("confidence", "yellow")}>Yellow ({counts.yellow})</Chip>
        <Chip active={confidence === "green"} onClick={() => set("confidence", "green")}>Green ({counts.green})</Chip>
        <span className="mx-2 h-5 w-px bg-slate-200" />
        <Chip active={status === "pending"} onClick={() => set("status", "pending")}>To review</Chip>
        <Chip active={status === "decided"} onClick={() => set("status", "decided")}>Done</Chip>
        <Chip active={!status} onClick={() => set("status", null)}>All</Chip>
        <select className={`${inputClass} ml-auto w-48`} value={params.get("question_id") ?? ""}
                onChange={(e) => set("question_id", e.target.value || null)}>
          <option value="">All questions</option>
          {exam.data?.questions.map((q) => <option key={q.id} value={q.id}>Question {q.label}</option>)}
        </select>
      </Card>

      {queue.isLoading && <Spinner />}
      <ErrorText error={queue.error} />
      {queue.data && queue.data.length === 0 && (
        <Card><p className="text-sm text-slate-600">Nothing here. {status === "pending" && "All answers matching this filter are reviewed."}</p></Card>
      )}
      {queue.data && queue.data.length > 0 && (
        <Card className="p-0">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500">
              <tr><th className="px-4 py-2">Roll number</th><th>Question</th><th>AI marks</th><th>Check</th><th>Confidence</th><th>Final</th></tr>
            </thead>
            <tbody>
              {queue.data.map((a) => (
                <tr key={a.id} className="cursor-pointer border-t border-slate-100 hover:bg-indigo-50/50"
                    onClick={() => navigate(`/exams/${examId}/review/${a.id}?${params.toString()}`)}>
                  <td className="px-4 py-2 font-medium">{a.roll_number}</td>
                  <td>Q{a.question_label}</td>
                  <td>{a.ai_marks ?? "–"} / {a.max_marks}</td>
                  <td className="text-slate-500">{a.check_marks ?? "–"}</td>
                  <td><ConfidenceBadge value={a.confidence} /></td>
                  <td>{a.final_marks ?? <span className="text-slate-400">pending</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
