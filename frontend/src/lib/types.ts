export type Role = "admin" | "coordinator" | "teacher";
export type Confidence = "green" | "yellow" | "red";
export type ScriptStatus = "uploaded" | "queued" | "processing" | "ready" | "reviewed" | "failed";
export type AnswerStatus = "pending" | "accepted" | "changed";

export interface Me {
  id: string;
  college_id: string;
  college_name: string | null;
  role: Role;
  full_name: string;
  email: string;
  employee_id: string | null;
}

export interface RubricPoint {
  id?: string;
  description: string;
  marks: number;
  position?: number;
}

export type QuestionType = "short" | "long" | "mcq";

export interface Question {
  id: string;
  label: string;
  text: string;
  max_marks: number;
  position: number;
  model_answer: string | null;
  qtype: QuestionType;
  correct_option: string | null;
  rubric_points: RubricPoint[];
}

export interface Exam {
  id: string;
  subject: string;
  exam_date: string | null;
  total_marks: number;
  created_at: string;
  script_counts?: Partial<Record<ScriptStatus, number>>;
}

export interface ExamDetail extends Exam {
  questions: Question[];
  rubric_problems: string[];
  question_paper_url: string | null;
}

export interface Script {
  id: string;
  exam_id: string;
  roll_number: string;
  page_count: number | null;
  status: ScriptStatus;
  error: string | null;
  attempts: number;
  assigned_to: string | null;
  assigned_at: string | null;
  assignee: { full_name: string; employee_id: string | null } | null;
  answers: Partial<Record<"total" | "decided" | Confidence, number>>;
}

export interface MyScript extends Script {
  exam: { subject: string; exam_date: string | null; total_marks: number };
}

export interface QueueItem {
  id: string;
  script_id: string;
  question_id: string;
  roll_number: string;
  question_label: string;
  max_marks: number;
  ai_marks: number | null;
  check_marks: number | null;
  confidence: Confidence;
  status: AnswerStatus;
  final_marks: number | null;
}

export interface PointBreakdown {
  point_number: number;
  description: string;
  max_marks: number;
  verdict: "full" | "partial" | "absent";
  marks: number;
  evidence_quote: string;
  reason: string;
}

export interface AnswerDetail {
  id: string;
  script_id: string;
  exam_id: string;
  roll_number: string;
  page_numbers: number[];
  transcription: string;
  ai_marks: number | null;
  ai_breakdown: PointBreakdown[];
  ai_reason: string | null;
  check_marks: number | null;
  check_breakdown: PointBreakdown[];
  confidence: Confidence;
  confidence_reasons: string[];
  status: AnswerStatus;
  question: Question;
  pages: { page_no: number; legibility: string | null; url: string; is_answer_page: boolean }[];
  final: { marks: number; comment: string | null; decided_at: string } | null;
}

export interface UserRow {
  id: string;
  full_name: string;
  email: string | null;
  employee_id: string | null;
  role: Role;
}
