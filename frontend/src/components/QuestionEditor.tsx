import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Question, QuestionType, RubricPoint } from "../lib/types";
import { Button, ErrorText, inputClass } from "./ui";

interface Props {
  examId: string;
  question?: Question;          // undefined = new question
  nextPosition: number;
  onDone: () => void;
}

export default function QuestionEditor({ examId, question, nextPosition, onDone }: Props) {
  const qc = useQueryClient();
  const [label, setLabel] = useState(question?.label ?? "");
  const [qtype, setQtype] = useState<QuestionType>(question?.qtype ?? "short");
  const [text, setText] = useState(question?.text ?? "");
  const [maxMarks, setMaxMarks] = useState(question ? String(question.max_marks) : "");
  const [correctOption, setCorrectOption] = useState(question?.correct_option ?? "");
  const [modelAnswer, setModelAnswer] = useState(question?.model_answer ?? "");
  const [points, setPoints] = useState<RubricPoint[]>(
    question?.rubric_points.length ? question.rubric_points : [{ description: "", marks: 1 }],
  );

  const isMcq = qtype === "mcq";
  const total = points.reduce((s, p) => s + (Number(p.marks) || 0), 0);
  const max = Number(maxMarks) || 0;

  const save = useMutation({
    mutationFn: () => {
      const body = {
        label: label.trim(), text, max_marks: max, model_answer: modelAnswer.trim() || null,
        position: question?.position ?? nextPosition,
        qtype,
        correct_option: isMcq ? correctOption.trim().toUpperCase() : null,
        rubric_points: isMcq ? [] : points.filter((p) => p.description.trim())
          .map((p) => ({ description: p.description.trim(), marks: Number(p.marks) })),
      };
      return question
        ? api.send("PUT", `/questions/${question.id}`, body)
        : api.send("POST", `/exams/${examId}/questions`, body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["exam", examId] });
      onDone();
    },
  });

  const setPoint = (i: number, patch: Partial<RubricPoint>) =>
    setPoints(points.map((p, j) => (i === j ? { ...p, ...patch } : p)));

  return (
    <div className="space-y-3 rounded-md border border-indigo-200 bg-indigo-50/40 p-3">
      <div className="grid grid-cols-8 gap-2">
        <label className="col-span-1 text-sm">
          Label
          <input className={inputClass} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="1, 2a…" />
        </label>
        <label className="col-span-2 text-sm">
          Type
          <select className={inputClass} value={qtype} onChange={(e) => setQtype(e.target.value as QuestionType)}>
            <option value="short">Short answer</option>
            <option value="long">Long answer</option>
            <option value="mcq">Multiple choice</option>
          </select>
        </label>
        <label className="col-span-4 text-sm">
          Question text {isMcq && <span className="text-slate-500">(put each option on its own line: "A. …")</span>}
          {isMcq ? (
            <textarea className={inputClass} rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          ) : (
            <input className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />
          )}
        </label>
        <label className="col-span-1 text-sm">
          Max marks
          <input className={inputClass} type="number" min="0.5" step="0.5" value={maxMarks}
                 onChange={(e) => setMaxMarks(e.target.value)} />
        </label>
      </div>

      {isMcq ? (
        <label className="block text-sm">
          Correct option
          <input className={`${inputClass} w-24 uppercase`} maxLength={1} value={correctOption} placeholder="B"
                 onChange={(e) => setCorrectOption(e.target.value.replace(/[^a-z]/gi, "").toUpperCase())} />
          <span className="ml-2 text-slate-500">Graded instantly by an exact rule — no AI needed.</span>
        </label>
      ) : (
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="font-medium">Rubric points</span>
            <span className={Math.abs(total - max) < 1e-6 ? "text-emerald-700" : "text-amber-700"}>
              {total} of {max} marks allocated
            </span>
          </div>
          <div className="space-y-2">
            {points.map((p, i) => (
              <div key={i} className="flex gap-2">
                <input className={inputClass} placeholder="What the answer must contain, e.g. 'Defines a stack as LIFO'"
                       value={p.description} onChange={(e) => setPoint(i, { description: e.target.value })} />
                <input className={`${inputClass} w-24`} type="number" min="0.5" step="0.5" value={p.marks}
                       onChange={(e) => setPoint(i, { marks: Number(e.target.value) })} />
                <Button variant="ghost" type="button" onClick={() => setPoints(points.filter((_, j) => j !== i))}
                        aria-label="Remove point">✕</Button>
              </div>
            ))}
          </div>
          <Button variant="ghost" type="button" className="mt-1"
                  onClick={() => setPoints([...points, { description: "", marks: 1 }])}>+ Add point</Button>
        </div>
      )}

      {!isMcq && (
        <label className="block text-sm">
          Model answer <span className="text-slate-500">(optional, helps the AI)</span>
          <textarea className={inputClass} rows={3} value={modelAnswer} onChange={(e) => setModelAnswer(e.target.value)} />
        </label>
      )}

      <div className="flex items-center gap-2">
        <Button onClick={() => save.mutate()}
                disabled={save.isPending || !label.trim() || !text.trim() || !max || (isMcq && !correctOption)}>
          Save question
        </Button>
        <Button variant="secondary" onClick={onDone}>Cancel</Button>
        <ErrorText error={save.error} />
      </div>
    </div>
  );
}
