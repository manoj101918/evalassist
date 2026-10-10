# EvalAssist: a beginner's guide to what we have built

This guide explains the whole project in plain language: what it does, which tools it uses and
why, how the pieces talk to each other, what happens step by step, what problems came up while
building and testing it, and how they were fixed. Technical words are explained when they first
appear, and there is a glossary at the end.

---

## 1. What EvalAssist is, in one paragraph

Teachers spend days marking hundreds of handwritten answer booklets after every exam. EvalAssist
is a website that helps them. The **exam cell coordinator** uploads the scanned booklets (PDFs).
An **AI** reads the handwriting, splits each booklet into answers, compares every answer with the
college's **marking scheme (rubric)**, suggests marks with reasons, and colours each answer
**green / yellow / red** by how confident it is. The coordinator **assigns** booklets to teachers.
Each teacher signs in with their **employee ID**, sees only **their** papers, and accepts or
changes every mark. **The teacher always makes the final decision.** Every decision is recorded,
and the final marks are exported to **Excel**.

---

## 2. The big picture

```
   ┌───────────────────────────┐
   │  Browser (the website)    │   what people see and click
   │  React app, port 5174     │
   └─────────────┬─────────────┘
                 │ asks for data / sends actions (HTTP requests)
                 ▼
   ┌───────────────────────────┐           ┌──────────────────────────────┐
   │  Backend API (FastAPI)    │           │  Worker (background program) │
   │  Python, port 8000        │           │  Python, runs all the time   │
   │  - checks who you are     │           │  - picks up uploaded scripts │
   │  - checks what you may do │           │  - runs the AI pipeline      │
   └─────────────┬─────────────┘           └───────┬──────────────┬───────┘
                 │ reads/writes                    │              │ sends pages & answers
                 ▼                                 ▼              ▼
   ┌──────────────────────────────────────────────────┐   ┌─────────────────────┐
   │  Supabase (in the cloud, Mumbai region)          │   │  Groq (AI in cloud) │
   │  - Database: exams, questions, answers, marks…   │   │  - reads handwriting│
   │  - Auth: user accounts and passwords             │   │  - grades answers   │
   │  - Storage: the PDF files and page images        │   └─────────────────────┘
   └──────────────────────────────────────────────────┘
```

There are **three programs running on your computer**, plus **two cloud services**:

| Program / service | Where | Job |
|---|---|---|
| **Frontend** (website) | your PC, `http://localhost:5174` | The screens people use |
| **Backend API** | your PC, `http://localhost:8000` | The "gatekeeper": receives every request from the website, checks the user's identity and permissions, reads and writes data |
| **Worker** | your PC, in the background | Does the slow AI work, so the website never has to wait |
| **Supabase** | cloud | Stores all data, user accounts and files |
| **Groq** | cloud | Runs the AI models |

> Why a separate worker? Grading one booklet takes minutes (many AI calls). If the website waited
> for that, it would freeze. So uploads just go into a **queue**, and the worker processes the
> queue one booklet at a time.

---

## 3. The tools we used, and why

### 3.1 Frontend (the website): folder `frontend/`

| Tool | What it is (simple) | Why we use it |
|---|---|---|
| **React** | A JavaScript library for building web pages out of reusable pieces called *components* | The most common way to build interactive websites |
| **TypeScript** | JavaScript with *types* (you declare "this is a number") | Catches mistakes before the code runs |
| **Vite** | A development tool that runs the website locally and builds it for production | Very fast; the page reloads instantly when code changes |
| **Tailwind CSS** | A styling system where you style with short class names (`text-sm`, `bg-white`) | Quick, consistent design without writing CSS files |
| **React Router** | Decides which page to show for each URL (`/`, `/exams/123`, …) | Multi-page navigation |
| **TanStack Query** | Fetches data from the API, caches it, refreshes it | Automatic refresh (e.g. script status updates every few seconds) |
| **supabase-js** | Supabase's JavaScript library | Keeps the signed-in session in the browser |

### 3.2 Backend (the API and worker): folder `backend/`

| Tool | What it is (simple) | Why we use it |
|---|---|---|
| **Python** | Programming language | Great for AI, PDFs and data |
| **FastAPI** | A Python framework for building APIs | Simple, fast, checks input automatically |
| **Uvicorn** | The server program that runs FastAPI | Makes the API reachable at port 8000 |
| **Pydantic** | Describes the exact shape of data (fields and types) | Validates requests and the AI's replies |
| **Groq SDK** (`groq`) | Groq's official Python library | Talks to the AI models |
| **supabase-py** | Supabase's Python library | Database, file storage, admin user creation |
| **PyMuPDF** | Reads PDF files | Turns each scanned page into an image |
| **openpyxl** | Creates Excel files | The marks export |
| **RapidFuzz** | "Fuzzy" text matching (finds nearly-matching text) | Checks the AI's quoted evidence really appears in the answer |
| **PyJWT** | Reads and verifies login tokens | Confirms who is making each request |
| **pytest** | Testing tool | Runs the 38 automatic tests |

### 3.3 Cloud services

| Service | What it gives us |
|---|---|
| **Supabase**, project `evalassist`, region **ap-south-1 (Mumbai)**, free plan | **PostgreSQL database** (tables), **Auth** (accounts and passwords), **Storage** (PDFs and images). Mumbai keeps student data in India. |
| **Groq** (free tier) | Very fast AI models. We use two:<br>• **`qwen/qwen3.8-27b`**, a *vision* model that can look at images and read handwriting<br>• **`openai/gpt-oss-120b`**, a text model for splitting and grading |

> We first planned to use Anthropic's Claude API. You asked to switch to **Groq**, so all AI calls
> now go to Groq.

---

## 4. The project folders and files

```
ai_evaluation_system/
├── README.md              ← setup and usage instructions
├── KNOWLEDGE.md           ← this guide
├── .gitignore             ← files git must never store (keys, big folders, samples)
│
├── supabase/migrations/   ← SQL files that created the database (run in order)
│   ├── 0001_schema.sql            all tables
│   ├── 0002_rls.sql               row-level security (who can read which rows)
│   ├── 0003_storage.sql           the private "scripts" file bucket
│   ├── 0004_advisor_fixes.sql     fixes suggested by Supabase's security checker
│   └── 0005_employee_id_assignment.sql   employee IDs + assigning scripts to teachers
│
├── backend/
│   ├── .env               ← SECRET settings (keys). Never share or commit this file!
│   ├── .env.example       ← the same settings with the secrets left blank (safe to share)
│   ├── pyproject.toml     ← list of Python libraries the backend needs
│   ├── app/
│   │   ├── main.py        ← starts the API and plugs in all the "routers"
│   │   ├── config.py      ← reads settings from .env; AI prices for cost estimates
│   │   ├── db.py          ← connection to Supabase; retry helper for network blips
│   │   ├── auth.py        ← "who is this user?" + role checks + "is this script yours?"
│   │   ├── access.py      ← loads a row only if it belongs to the user's college
│   │   ├── audit.py       ← writes one audit-log row for every important action
│   │   ├── pdf.py         ← PDF → page images; detects blank pages
│   │   ├── questions_repo.py ← loads questions + rubric; checks rubric totals
│   │   ├── export.py      ← builds the Excel workbook
│   │   ├── worker.py      ← the background worker (queue → AI → save)
│   │   ├── routers/       ← the API endpoints, grouped by topic
│   │   │   ├── session.py    sign-in with employee ID or email
│   │   │   ├── users.py      "who am I", list users, add users
│   │   │   ├── exams.py      create/list/edit exams, question paper upload
│   │   │   ├── questions.py  questions and rubric points
│   │   │   ├── scripts.py    upload booklets, assign to teachers, "my papers"
│   │   │   ├── review.py     review queue, open an answer, accept/change marks
│   │   │   └── export.py     download the Excel file
│   │   └── ai/            ← the AI "agent"
│   │       ├── client.py     talks to Groq: JSON replies, rate-limit waits, cost tracking
│   │       ├── prompts.py    the instructions given to the AI for each step
│   │       ├── schemas.py    the exact shape of each AI reply
│   │       ├── pipeline.py   the steps: read → split → grade ×2 → decide colour
│   │       ├── confidence.py the green/yellow/red rules
│   │       └── evidence.py   checks quoted evidence exists in the answer
│   ├── scripts/
│   │   ├── seed.py           creates the first college + admin account
│   │   ├── run_pipeline.py   runs the AI on one PDF from the command line (no website)
│   │   └── sample_rubric.json an example rubric file
│   └── tests/             ← 38 automatic tests
│
├── frontend/
│   ├── .env               ← website settings (Supabase URL, public key, API address)
│   ├── package.json       ← list of JavaScript libraries
│   └── src/
│       ├── main.tsx       ← starts the app; decides which page each URL shows
│       ├── lib/           ← helpers: api.ts (calls the backend), auth.tsx (login state),
│       │                     supabase.ts, types.ts (data shapes)
│       ├── components/    ← reusable pieces: Layout (top bar), ui (buttons, badges),
│       │                     QuestionEditor (rubric editor)
│       └── pages/         ← one file per screen:
│           ├── Login.tsx        sign in with employee ID (or email for admins)
│           ├── MyPapers.tsx     teacher's list of assigned booklets
│           ├── Exams.tsx        list of exams (coordinator/admin)
│           ├── ExamDetail.tsx   questions, rubric, upload, assign to teachers
│           ├── ReviewQueue.tsx  list of answers to review, with filters
│           ├── ReviewAnswer.tsx the marking screen (handwriting | AI reading | marks)
│           └── Users.tsx        add teachers/coordinators (admin)
│
└── samples/               ← test data and logs (ignored by git)
    ├── mendeley_ds_exam/  ← real handwritten exam booklets from a public research dataset
    ├── result_student1.json, run_student1.log   first AI test results
    └── api.log, worker.log, frontend.log        logs of the running programs
```

---

## 5. The database (what is stored)

Think of each **table** as a spreadsheet tab. All tables live in Supabase.

| Table | One row is… | Important columns |
|---|---|---|
| `colleges` | a college | name, plan |
| `profiles` | a person who can sign in | full name, **employee ID**, role (admin / coordinator / teacher), college |
| `exams` | an exam | subject, date, total marks |
| `questions` | a question in an exam | label ("21"), text, max marks, model answer |
| `rubric_points` | one marking point of a question | description, marks |
| `scripts` | one student's booklet | roll number, PDF location, status, **assigned teacher** |
| `script_pages` | one page of a booklet | page image location, AI transcription, legibility |
| `answers` | one student's answer to one question | AI marks, AI reasons, checker marks, colour, status |
| `final_marks` | the teacher's decision on an answer | marks, who decided, when, comment |
| `audit_log` | one recorded action | who, what, when, before → after |
| `ai_calls` | one AI request | model, tokens used, cost in USD |

**Script status** moves like this:

```
queued ("Waiting for AI") → processing ("AI reading…") → ready ("Ready to review") → reviewed
                                  └── on repeated errors → failed (coordinator can press Retry)
```

**Privacy:** students are stored only by **roll number**, never by name. Files are in a
**private** storage bucket; the website only gets short-lived links (valid 1 hour) to view page
images.

---

## 6. Users, roles and signing in

| Role | Signs in with | Can do |
|---|---|---|
| **Admin** | email (or employee ID) | Everything, including adding users |
| **Exam cell coordinator** | **employee ID** | Create exams and rubrics, upload booklets, **assign booklets to teachers**, retry failed booklets, export Excel |
| **Teacher** | **employee ID** | See **only** booklets assigned to them, evaluate them (accept/change marks) |

**How employee-ID sign-in works** (Supabase only understands emails, so the backend helps):

1. The teacher types `EMP1001` and a password on the login page.
2. The website sends both to our backend (`POST /auth/login`).
3. The backend finds the account with that employee ID, signs in with Supabase on the teacher's
   behalf, and returns a **session token** (a signed "pass" that proves who you are).
4. The website stores the token and attaches it to every later request.
5. On every request the backend checks the token's signature and looks up the user's role.

Safety details:
- Employee IDs are case-insensitive (`emp1001` works too) and unique in the whole system.
- A wrong password and an unknown employee ID give the **same** error message, so nobody can
  discover which employee IDs exist.
- Wildcard tricks (typing `%`) are blocked by an exact match.
- Teachers don't need an email; the system gives them an internal placeholder address that is
  never used for mail.

**Demo accounts in your database** (passwords were given to you in the chat; they are not written
here, so they can't leak if this file is shared):

| Name | Sign in with | Role |
|---|---|---|
| Exam Cell Admin | `admin@example.com` | admin |
| Exam Cell Coordinator | `EXC001` | coordinator |
| Priya Sharma | `EMP1001` | teacher |
| Ravi Kumar | `EMP1002` | teacher |

---

## 7. The complete flow, step by step

### Step 1: Exam setup (coordinator)
1. Sign in → **Exams** → **New exam** (subject, date, total marks).
2. Add each question with its **rubric points** (what the answer must contain, and marks for
   each). The screen shows "X of Y marks allocated"; the system refuses to grade until every
   question's points add up exactly to its max marks.
3. Optionally upload the question paper PDF.

### Step 2: Upload booklets (coordinator)
4. Drag and drop the scanned PDFs, **one PDF per student, named by roll number**
   (e.g. `21CS045.pdf` → roll number `21CS045`).
5. Each file is checked (is it a PDF? under 50 MB? duplicate roll number?), saved to storage,
   and marked **queued**.

### Step 3: AI processing (automatic, worker)
6. The worker notices the queued booklet and runs the AI pipeline (explained in section 8).
7. When done, the booklet becomes **ready**, with suggested marks and a colour for every answer.

### Step 4: Assign booklets (coordinator)
8. On the exam page, each booklet has an **Assigned to** dropdown. The coordinator can also:
   - tick several booklets → "Assign N selected to [teacher]", or
   - **Distribute unassigned…** → tick the teachers of this subject → booklets are shared
     evenly (it counts what each teacher already has).
9. Chips like "Priya Sharma: 3/10 evaluated" show each teacher's progress.

### Step 5: Evaluation (teacher)
10. The teacher signs in with their employee ID and lands on **My papers**: their booklets grouped
    by exam, with a progress bar and red/yellow/green counts.
11. **Start evaluation** (or **Continue**) opens the first unmarked answer. The marking screen has
    three panels:
    - **Left:** the original handwritten page image (zoomable)
    - **Middle:** the AI's reading (transcription) of the answer
    - **Right:** the suggested marks per rubric point, each with a **quote from the answer as
      evidence** and a reason; the colour and why; the checker's marks
12. Press **`a`** to accept, or **`c`** to change (type the marks, optional comment). The next
    answer opens automatically. `j`/`k` move to the next or previous answer. After the last answer
    the teacher returns to My papers.
13. **Accept all green** (on My papers) accepts every green answer of a booklet in one click; each
    one is still recorded separately in the audit log.

### Step 6: Results (coordinator)
14. **Export to Excel** gives three sheets:
    - **Marks:** one row per student, one column per question, total, "Complete / N pending"
    - **Detail:** every answer with AI mark, checker mark, colour, final mark, who decided, when
    - **Pilot metrics:** how often the AI was right, average difference from teacher marks,
      colour mix, **AI cost per booklet** (useful for pricing and for a pilot case study)

---

## 8. How the AI "agent" works (the pipeline)

The code is in `backend/app/ai/pipeline.py`. For each booklet:

```
PDF ──► 1. page images ──► 2. skip blank pages ──► 3. READ each page (vision AI)
    ──► 4. SPLIT into answers (text AI) ──► 5. GRADE each answer (text AI)
    ──► 6. CHECK: grade again strictly + verify evidence ──► 7. COLOUR ──► 8. SAVE
```

1. **Page images.** PyMuPDF turns each PDF page into a grey-scale PNG image (150 dpi). The same
   images are shown to teachers in the marking screen.
2. **Blank page detection.** Scanners often capture the back of a sheet showing faint
   mirror-image "bleed-through" of the other side. The AI invents text for such pages, so we
   count dark "ink" pixels first: real pages have ≥0.2% ink, blank backs ≤0.02%. Pages under 0.05%
   are skipped (no AI call, no cost).
3. **Read (transcribe).** Each page image goes to the **vision model** with instructions: copy
   exactly what's written, keep question numbers, write `[illegible]` for unreadable words,
   describe diagrams as `[diagram: …]`, ignore bleed-through. The reply is plain text. From that
   text our code works out:
   - **legibility:** clear (no `[illegible]`), partial, or unreadable (over 30% illegible)
   - **question numbers** found on the page
   - **diagram or maths present** (from the `[diagram: …]` / `[math: …]` notes)
4. **Split (segment).** One call to the text model with all page transcriptions plus the exam's
   question list. It returns, for each question, which pages the answer is on and the exact
   answer text. It handles answers written out of order and answers continued later, and flags
   anything ambiguous. (In the Student_1 test it noticed an answer labelled "29" was really
   question 25 and flagged it.)
5. **Grade.** For every answer, the text model gets the question, the rubric, the model answer and
   the student's answer. For **each rubric point** it returns: full / partial / absent, marks, a
   **word-for-word quote** from the answer as evidence, and a one-sentence reason. Our code then
   **clamps** the marks: never below 0, never above the point's maximum, in steps of 0.5.
6. **Double-check.** A second, stricter "checker" grades the same answer **independently**. Our
   code also searches for every quoted piece of evidence in the answer (fuzzy match, so small
   spelling differences are fine). A quote that can't be found suggests the AI made something up.
7. **Colour** (`confidence.py`):

   | Colour | Meaning | When |
   |---|---|---|
   | 🟢 **Green** | Probably right, quick approval | Handwriting clear, both gradings within 0.5 marks, all evidence found |
   | 🟡 **Yellow** | Check the reasoning | Some words illegible, gradings differ slightly, evidence not found, or no answer found on clear pages |
   | 🔴 **Red** | Grade carefully | Page unreadable, diagram or maths, gradings differ by more than 25% of the marks, unclear where the answer starts or ends, or the AI failed on this answer |

8. **Save.** Pages, answers and costs are written to the database, and the booklet becomes
   **ready**.

**Why is this called an "agent"?** Because it isn't one AI question: it's several steps that
check each other (read → split → grade → re-grade → verify evidence → decide).

**Why the AI replies in JSON:** for splitting and grading we force the model to reply in an exact
structure (**JSON schema**), such as `{"points":[{"point_number":1,"verdict":"full","marks":2,...}]}`,
so our code can read it reliably. The vision model is the exception (see problem 3 below).

---

## 9. Problems we met, and how we fixed them

Real testing found real problems. Each fix is in the code now.

| # | Problem | What we saw | Fix |
|---|---|---|---|
| 1 | Switch AI provider | You asked to use Groq instead of Claude | Rewrote `ai/client.py` for Groq; model names are settings in `.env` |
| 2 | Free-tier limits | Groq free tier allows only ~8,000 tokens per minute per model, and the vision model only ~1,000 output tokens per minute (about **1 page per minute**) | Each step asks for a realistic output size; when Groq says "rate limited, try again in 35s", the code **waits and retries** instead of failing |
| 3 | Vision model produced garbage in JSON mode | Asked for JSON, it returned `⚜︎︎︎︎…` or random Japanese text, even for clear pages | Tested alternatives: **plain-text transcription is almost word-perfect**. So the vision step returns plain text and our code derives legibility, question numbers and diagram flags itself |
| 4 | AI "read" blank pages | Page 4 of every booklet is the blank back of a sheet with bleed-through; the AI invented whole answers | Ink-pixel blank detection skips those pages (section 8, step 2) |
| 5 | Grading replies cut off | At "high" reasoning effort the model spent its whole budget thinking, so its JSON was incomplete | Use "medium" effort; retry a cut-off reply once with double the budget |
| 6 | One bad answer killed the whole booklet | A single failed AI call stopped all 35 answers | That answer is marked **red, "please grade manually"**; the others continue |
| 7 | Unstable internet | Many "DNS lookup failed" / "connection forcibly closed" errors on this PC | Database steps retry up to 5 times; Groq calls retry dropped connections; the worker never crashes on a network blip |
| 8 | Worker crashed | A DNS error while checking the queue stopped the worker | The worker's main loop now logs the error, waits 15 s and continues |
| 9 | Student_2 stuck in "AI evaluating" | Saving a cost row after every AI call failed on a network drop, and the whole booklet restarted each time | Costs are saved **once at the end**, and a failed cost save never fails a booklet |
| 10 | Silent long waits | If a daily Groq limit is reached, "try again in 2 hours" would make the worker wait silently | Waits over 90 s stop the booklet with a clear message ("Groq usage limit reached, resets in …"); the coordinator presses **Retry** later. The worker log now shows every AI call |
| 11 | Port already in use | Port 5173 was used by your other project `doctor_dashboard` | EvalAssist's website runs on **5174**; we didn't touch the other project |
| 12 | Secret key in the wrong file | The Supabase service-role key had been pasted into `.env.example` (a file meant to be shared) | Moved it to `.env` (ignored by git) and blanked the example file |
| 13 | Dataset inconsistency | The sample dataset's MCQ totals don't match its own answer key | We compare the AI only on the 15 short answers, whose per-question teacher marks are reliable |

---

## 10. Test results so far

### Sample data
We used a public research dataset (Mendeley Data, licence CC BY 4.0): **50 real scanned
handwritten university exam booklets** (Data Science, 20 MCQs + 15 two-mark short answers = 50
marks), with the answer key and the **teacher's marks for every question**. Three booklets
(Student_1, 2 and 3) are in `samples/mendeley_ds_exam/`. The dataset credit is in `SOURCE.md` there.

### Student_1 (command-line test)
- Reading handwriting: accurate; answers written out of order were matched correctly.
- MCQs: all correctly marked against the answer key (one call failed due to the network and was
  flagged red, as designed).
- Short answers vs the teacher: **9 of 15 exactly the same**, average difference **0.47 marks**.
  When different, the AI was **stricter** than the teacher (gave 0 where the teacher gave 1 for
  vague but relevant answers).
- Cost: **about $0.03 (≈ ₹2.5) per 4-page booklet** on Groq.

### Student_2 (full website flow)
- Graded in the background: **62 AI calls, $0.0245**, about **32 minutes** (free-tier waits plus
  network retries; a paid tier would take about a minute).
- Result: 35 answers, **22 green, 6 yellow, 7 red**, assigned to Priya (EMP1001), ready to
  evaluate.

### Automatic tests
**38 tests pass** (`cd backend && .venv\Scripts\python -m pytest`). They cover the colour rules,
evidence matching, the pipeline (with a fake AI), mark clamping, the Excel file, PDF rendering,
blank-page detection, rate-limit handling, employee-ID rules and balanced assignment.

### Login and permission checks (run against the live system)
- Admin, coordinator and teachers sign in correctly.
- A teacher sees only their own papers; another teacher is refused access to them.
- Teachers cannot assign papers or add users; coordinators cannot add users.
- Wrong passwords, unknown IDs and wildcard tricks are rejected.

---

## 11. Security, in simple words

- **Secrets** (Supabase service key, Groq API key) live only in `backend/.env`, which git ignores.
  The website only has the **public** Supabase key, which is safe to expose.
- **Every** request to the API must carry a valid session token; the backend verifies it.
- **Roles** are checked on every action (e.g. only admins add users).
- **Teachers** can only open and mark scripts assigned to them.
- **Colleges are separated:** every query is limited to the user's own college. Supabase
  **Row Level Security (RLS)** adds a second lock inside the database.
- **Audit log:** every important action (upload, assign, accept, change, export, …) records who,
  when, and the before/after values. This helps with re-evaluation requests.
- **Data location:** Supabase in Mumbai (India).

---

## 12. How to run it

Open three terminals.

**1. Backend API** (from the `backend` folder):
```
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```
**2. Worker** (from the `backend` folder):
```
.venv\Scripts\python -m app.worker
```
**3. Website** (from the `frontend` folder):
```
npm run dev -- --port 5174
```
Then open **http://localhost:5174**.

**Useful extras**
- Run the AI on one PDF without the website (prints marks, colours, cost, and comparison with the
  teacher's marks):
  ```
  .venv\Scripts\python scripts\run_pipeline.py ..\samples\mendeley_ds_exam\Student_Pdf\Student_1.pdf ..\samples\mendeley_ds_exam\rubric.json --teacher-marks ..\samples\mendeley_ds_exam\teacher_marks\Student_1.json
  ```
- Create a new college and admin: `.venv\Scripts\python scripts\seed.py --college "..." --email ... --name "..." --password "..."`
- Logs: `samples/worker.log` (AI progress and errors), `samples/api.log`, `samples/frontend.log`.

**Settings** (`backend/.env`):

| Setting | Meaning |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Connection to the database (secret key!) |
| `GROQ_API_KEY` | Your Groq key (secret!) |
| `GROQ_VISION_MODEL` | Reads handwriting (default `qwen/qwen3.8-27b`) |
| `GROQ_GRADING_MODEL` | Splits and grades (default `openai/gpt-oss-120b`) |
| `GROQ_CHECK_MODEL` | Second, independent grading (default same as grading) |
| `MAX_PARALLEL_CALLS` | How many AI calls at once |
| `CORS_ORIGINS` | Which website addresses may call the API (5173 and 5174) |

---

## 13. Known limitations and next steps

1. **Speed on Groq's free tier:** about 30 minutes per booklet on this connection. For a real
   pilot, use Groq's paid "Dev tier" (≈1 minute per booklet) and host the backend on a server with
   stable internet.
2. **The AI is stricter than the sample teacher.** Better rubrics help: split each 2-mark question
   into two 1-mark points (e.g. "names the concept" + "explains it") so the AI can give partial
   credit.
3. **Some green answers still differed from the teacher.** Using a *different* model for the
   checker (`GROQ_CHECK_MODEL`) would make the double-check more independent.
4. **Diagrams and maths** are flagged red for the teacher; the AI doesn't grade them yet.
5. **Assignment is per booklet** (a teacher marks all questions of a booklet). Assigning by
   question (Teacher A marks Q1–10 of every booklet) would be a new feature.
6. **Teachers can still edit rubrics.** We can lock rubrics once evaluation starts.
7. **Later features** from the original plan: AI-drafted rubrics, student feedback reports,
   analytics, Telugu/Hindi answers, plagiarism detection, ERP integration, deployment to the
   internet.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Frontend** | The part you see: the website in the browser |
| **Backend** | Programs on a server that store data and enforce rules |
| **API** | A set of URLs the website calls to get data or perform actions (e.g. `GET /my/scripts`) |
| **Endpoint** | One such URL plus its method (GET = read, POST = create/do, PUT = replace, DELETE = remove) |
| **localhost / port** | "This computer" / a numbered door a program listens on (8000 = API, 5174 = website) |
| **Database / table / row** | Organised storage; a table is like a spreadsheet tab; a row is one record |
| **Migration** | A SQL file that changes the database structure, applied in order |
| **SQL / PostgreSQL** | The language for databases / the database engine Supabase uses |
| **Row Level Security (RLS)** | Database rules deciding which rows each user may see |
| **Auth / session token / JWT** | Sign-in system / a signed pass proving who you are / the token format |
| **Service-role key** | A master key for the database; secret, backend only |
| **Publishable (anon) key** | A public key for the browser; safe to expose |
| **Storage bucket** | A folder in the cloud for files (our PDFs and page images) |
| **Signed URL** | A temporary link to a private file (expires after 1 hour) |
| **Worker / queue** | A background program / the list of jobs waiting for it |
| **LLM / AI model** | Large Language Model: the AI that reads and writes text (some also see images) |
| **Vision model** | An AI model that can understand images |
| **Prompt** | The instructions we give the AI |
| **Token** (AI) | A piece of a word; AI usage and cost are counted in tokens |
| **Rate limit** | A cap on how much you may use per minute or day (e.g. 8,000 tokens/minute) |
| **JSON / JSON schema** | A text format for structured data / a description of the exact fields expected |
| **Transcription** | Turning handwriting into typed text |
| **Segmentation** | Splitting the booklet's text into answers per question |
| **Rubric** | The marking scheme: the points an answer should contain, with marks for each |
| **Audit log** | A permanent record of who did what and when |
| **CORS** | A browser safety rule; the API must list which websites may call it |
| **`.env` file** | A file of settings and secrets, read when a program starts |
| **SDK / library** | Ready-made code for using a service or doing a task |
| **pytest / test** | A tool / small program that checks the code works as expected |
| **Dependency** | A library the project needs, installed with `pip` (Python) or `npm` (JavaScript) |
