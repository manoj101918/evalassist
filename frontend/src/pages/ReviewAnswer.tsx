import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { AnswerDetail, PointBreakdown } from "../lib/types";
import { Button, Card, ConfidenceBadge, ErrorText, Spinner, inputClass } from "../components/ui";
import { useQueue } from "./ReviewQueue";

const VERDICT_STYLE = { full: "text-emerald-700", partial: "text-amber-700", absent: "text-slate-400" };

function PageImages({ pages }: { pages: AnswerDetail["pages"] }) {
  const [showAll, setShowAll] = useState(false);
  const [zoom, setZoom] = useState(1);
  const shown = showAll ? pages : pages.filter((p) => p.is_answer_page);
  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center gap-2 text-sm">
        <span className="font-medium">Original handwriting</span>
        <Button variant="ghost" onClick={() => setZoom(Math.max(0.5, zoom - 0.25))}>−</Button>
        <span>{Math.round(zoom * 100)}%</span>
        <Button variant="ghost" onClick={() => setZoom(Math.min(3, zoom + 0.25))}>+</Button>
        <label className="ml-auto flex items-center gap-1 text-slate-600">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> all pages
        </label>
      </div>
      <div className="flex-1 space-y-3 overflow-auto rounded border border-slate-200 bg-slate-100 p-2">
        {shown.map((p) => (
          <figure key={p.page_no}>
            <figcaption className="text-xs text-slate-500">
              Page {p.page_no}{p.legibility && p.legibility !== "clear" && ` · ${p.legibility}`}
            </figcaption>
            <img src={p.url} alt={`Page ${p.page_no}`} style={{ width: `${zoom * 100}%`, maxWidth: "none" }}
                 className="bg-white shadow" />
          </figure>
        ))}
        {shown.length === 0 && <p className="p-4 text-sm text-slate-500">No pages matched this answer. Tick "all pages" to look through the booklet.</p>}
      </div>
    </div>
  );
}

function Breakdown({ points, check }: { points: PointBreakdown[]; check: PointBreakdown[] }) {
  const checkBy = new Map(check.map((p) => [p.point_number, p]));
  return (
    <ol className="space-y-2">
      {points.map((p) => {
        const c = checkBy.get(p.point_number);
        return (
          <li key={p.point_number} className="rounded border border-slate-200 p-2 text-sm">
            <div className="flex gap-2">
              <span className="flex-1 font-medium">{p.point_number}. {p.description}</span>
              <span className={`whitespace-nowrap font-semibold ${VERDICT_STYLE[p.verdict]}`}>
                {p.marks} / {p.max_marks}
              </span>
            </div>
            {p.evidence_quote && <blockquote className="mt-1 border-l-2 border-indigo-300 pl-2 italic text-slate-700">“{p.evidence_quote}”</blockquote>}
            <p className="mt-1 text-slate-600">{p.reason}</p>
            {c && c.marks !== p.marks && (
              <p className="mt-1 text-xs text-amber-700">Checker gave {c.marks}: {c.reason}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function ReviewAnswer() {
  const { examId = "", answerId = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const queue = useQueue(examId, params);
  const answer = useQuery({
    queryKey: ["answer", answerId],
    queryFn: () => api.get<AnswerDetail>(`/answers/${answerId}`),
  });
  const [changing, setChanging] = useState(false);
  const [marks, setMarks] = useState("");
  const [comment, setComment] = useState("");
  const marksInput = useRef<HTMLInputElement>(null);

  const ids = queue.data?.map((a) => a.id) ?? [];
  const index = ids.indexOf(answerId);
  const nextId = index >= 0 ? ids[index + 1] : ids[0];
  const prevId = index > 0 ? ids[index - 1] : undefined;
  const scriptMode = params.has("script_id");  // opened from "My papers" for one script
  const go = (id: string | undefined) => {
    if (id) navigate(`/exams/${examId}/review/${id}?${params.toString()}`);
    else if (scriptMode) navigate("/my-papers");  // finished this script
    else navigate(`/exams/${examId}/review?${params.toString()}`);
  };

  useEffect(() => {
    setChanging(false);
    setComment("");
    setMarks("");
  }, [answerId]);

  const decide = useMutation({
    mutationFn: (body: { action: "accept" | "change"; marks?: number; comment?: string }) =>
      api.send("POST", `/answers/${answerId}/decision`, body),
    onSuccess: () => {
      const target = nextId;
      qc.invalidateQueries({ queryKey: ["queue", examId] });
      qc.invalidateQueries({ queryKey: ["answer", answerId] });
      qc.invalidateQueries({ queryKey: ["scripts", examId] });
      qc.invalidateQueries({ queryKey: ["my-scripts"] });
      go(target);
    },
  });

  const a = answer.data;
  const accept = () => a && decide.mutate({ action: "accept", comment: comment || undefined });
  const submitChange = () => {
    if (marks === "") return;
    decide.mutate({ action: "change", marks: Number(marks), comment: comment || undefined });
  };
  const startChange = () => {
    setChanging(true);
    setMarks(String(a?.final?.marks ?? a?.ai_marks ?? ""));
    setTimeout(() => marksInput.current?.focus(), 0);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "a") accept();
      else if (e.key === "c") { e.preventDefault(); startChange(); }
      else if (e.key === "j") go(nextId);
      else if (e.key === "k" && prevId) go(prevId);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (answer.isLoading) return <Spinner />;
  if (!a) return <ErrorText error={answer.error} />;

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={scriptMode ? "/my-papers" : `/exams/${examId}/review?${params.toString()}`}
              className="text-sm text-slate-500 hover:underline">← {scriptMode ? "My papers" : "Queue"}</Link>
        <h1 className="text-lg font-semibold">Roll {a.roll_number} · Question {a.question.label}</h1>
        <ConfidenceBadge value={a.confidence} long />
        {a.status !== "pending" && (
          <span className="rounded bg-slate-100 px-2 py-0.5 text-xs">
            {a.status === "accepted" ? "Accepted" : "Changed"} · final {a.final?.marks}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2 text-sm text-slate-500">
          {index >= 0 && <span>{index + 1} of {ids.length}</span>}
          <Button variant="secondary" disabled={!prevId} onClick={() => go(prevId)}>← Prev (k)</Button>
          <Button variant="secondary" onClick={() => go(nextId)}>Next (j) →</Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 lg:grid-cols-12">
        <Card className="min-h-0 lg:col-span-5"><PageImages pages={a.pages} /></Card>

        <Card className="flex min-h-0 flex-col lg:col-span-3">
          <h2 className="mb-2 text-sm font-medium">AI reading of the answer</h2>
          <div className="flex-1 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono text-sm leading-relaxed">
            {a.transcription || <span className="text-slate-400">No answer found for this question.</span>}
          </div>
        </Card>

        <Card className="flex min-h-0 flex-col lg:col-span-4">
          <div className="flex-1 space-y-3 overflow-auto">
            <div>
              <p className="text-sm text-slate-600">{a.question.text}</p>
            </div>
            <div className="flex items-baseline gap-3">
              <span className="text-3xl font-semibold">{a.ai_marks ?? 0}</span>
              <span className="text-slate-500">/ {a.question.max_marks} suggested</span>
              <span className="ml-auto text-sm text-slate-500">checker: {a.check_marks ?? "–"}</span>
            </div>
            <ul className="space-y-0.5 text-sm">
              {a.confidence_reasons.map((r) => <li key={r}>• {r}</li>)}
            </ul>
            {a.ai_reason && <p className="rounded bg-indigo-50 p-2 text-sm">{a.ai_reason}</p>}
            <Breakdown points={a.ai_breakdown} check={a.check_breakdown} />
          </div>

          <div className="mt-3 space-y-2 border-t border-slate-200 pt-3">
            {changing && (
              <div className="flex gap-2">
                <input ref={marksInput} className={`${inputClass} w-28`} type="number" min="0" step="0.5"
                       max={a.question.max_marks} value={marks} onChange={(e) => setMarks(e.target.value)}
                       onKeyDown={(e) => e.key === "Enter" && submitChange()} placeholder="Marks" />
                <span className="self-center text-sm text-slate-500">/ {a.question.max_marks}</span>
              </div>
            )}
            <input className={inputClass} placeholder="Comment (optional)" value={comment}
                   onChange={(e) => setComment(e.target.value)} />
            <div className="flex gap-2">
              {changing ? (
                <>
                  <Button onClick={submitChange} disabled={decide.isPending || marks === ""}>Save marks</Button>
                  <Button variant="secondary" onClick={() => setChanging(false)}>Cancel</Button>
                </>
              ) : (
                <>
                  <Button onClick={accept} disabled={decide.isPending} className="flex-1">
                    Accept {a.ai_marks ?? 0} (a)
                  </Button>
                  <Button variant="secondary" onClick={startChange} className="flex-1">Change (c)</Button>
                </>
              )}
            </div>
            <ErrorText error={decide.error} />
          </div>
        </Card>
      </div>
    </div>
  );
}
