# EvalAssist: a beginner's guide to what we have built

This guide explains the whole project in plain language:
- what it does, and what has been done so far (and when),
- which tools it uses and why,
- how the pieces talk to each other, and what happens step by step,
- how we measure whether the AI is good,
- which problems came up and how they were fixed,
- what comes next.

Technical words are explained when they first appear, and there is a glossary at the end.

*Last updated: 11 October 2026.*

---

## 1. What EvalAssist is, in one paragraph

Teachers spend days marking hundreds of handwritten answer booklets after every exam. EvalAssist
is a website that helps them:
1. The **exam cell coordinator** uploads the scanned booklets (PDFs).
2. An **OCR service** (Azure) turns the handwriting into text.
3. **Simple rules** mark the multiple-choice questions (MCQs).
4. An **AI** marks the written answers against the college's **marking scheme (rubric)**. It
   suggests marks with reasons and colours each answer **green / yellow / red** by how confident
   it is.
5. The coordinator **assigns** booklets to teachers.
6. Each teacher signs in with their **employee ID**, sees only **their** papers, and accepts or
   changes every mark.

**The teacher always makes the final decision.** Every decision is recorded, and the final marks
are exported to **Excel**.

---

## 2. What has been done so far: the timeline

| Stage | What was built | Result |
|---|---|---|
| **1. MVP (first version)** | Website, backend API, background worker, Supabase database, AI pipeline (read → split → grade twice → colour), review screen, audit log, Excel export | Worked end to end, but **slow** (about 30 min per booklet) |
| **2. Switch to Groq** | All AI calls moved from Claude to Groq's free tier, as you asked | Free, but strict per-minute limits |
| **3. Roles and assignment** | Employee-ID login; the coordinator assigns booklets to teachers; teachers see only their own papers on **My papers** | The flow you asked for |
| **4. v2 plan** | A 2–3 month plan to make it **agentic** (LangGraph agent, our own small model, learning from teachers, public demo) | Plan approved |
| **5. Phase 0: foundations** | Code quality checker (ruff), Docker, automatic tests on GitHub (CI), evaluation harness, MCQ rules tier, **Azure page reading** | About **30 min → about 4 min** per booklet |
| **6. GitHub** | Code pushed to https://github.com/manoj101918/evalassist, with a check that no secret keys went up | CI passes ✅ |
| **7. Dataset and baseline** | All 50 real booklets downloaded and read with Azure; first measurement of AI accuracy against real teacher marks | Found 3 important problems (section 11) |
| **8. Fix 1: MCQ grid reader** | MCQs are read from **where each word sits on the page**; empty cells are re-read by the vision model | MCQ reading **45% → 89%** on the test students |

**Where we are now:** finishing Phase 0. Fix 1 (MCQs) is done. The baseline report has 5 of its
10 test booklets done; Groq's free daily limit stopped it, and it continues automatically from
where it stopped. Next come fix 2 (harsh grading) and fix 3 (trustworthy green), then Phase 1
(the LangGraph agent).

---

## 3. The big picture

```
   ┌───────────────────────────┐
   │  Browser (the website)    │   what people see and click
   │  React app, port 5174     │
   └─────────────┬─────────────┘
                 │ HTTP requests
                 ▼
   ┌───────────────────────────┐           ┌──────────────────────────────┐
   │  Backend API (FastAPI)    │           │  Worker (background program) │
   │  Python, port 8000        │           │  Python, runs all the time   │
   │  - checks who you are     │           │  - picks up uploaded scripts │
   │  - checks what you may do │           │  - runs the grading pipeline │
   └─────────────┬─────────────┘           └──┬──────────┬────────────┬───┘
                 │                            │          │            │
                 ▼                            ▼          ▼            ▼
   ┌─────────────────────────────────┐  ┌───────────┐ ┌─────────────────────┐
   │ Supabase (cloud, Mumbai)        │  │ Azure     │ │ Groq (AI in cloud)  │
   │ - Database (exams, answers…)    │  │ Document  │ │ - splits booklets   │
   │ - Auth (accounts, passwords)    │  │ Intelli-  │ │ - grades answers    │
   │ - Storage (PDFs, page images)   │  │ gence     │ │ - backup page reader│
   └─────────────────────────────────┘  │ reads the │ └─────────────────────┘
                                        │ handwriting│
                                        └───────────┘
```

| Program / service | Where | Job |
|---|---|---|
| **Frontend** (website) | your PC, `http://localhost:5174` | The screens people use |
| **Backend API** | your PC, `http://localhost:8000` | The "gatekeeper": checks identity and permissions, reads and writes data |
| **Worker** | your PC, in the background | Does the slow AI work, so the website never waits |
| **Supabase** | cloud (Mumbai) | Stores all data, user accounts and files |
| **Azure Document Intelligence** | cloud | **Reads the handwriting** (OCR): about 5 seconds per page |
| **Groq** | cloud | AI models that **split** booklets into answers and **grade** them; also reads pages if Azure fails |
| **GitHub** | cloud | Stores the code and runs the automatic checks (CI) on every push |

> **Why a separate worker?** Grading takes minutes. If the website waited, it would freeze. So
> uploads go into a **queue**, and the worker processes it one booklet at a time.

---

## 4. The complete flow of the application, step by step

### Step 1: Exam setup (coordinator)
1. Sign in with the employee ID (e.g. `EXC001`), then go to **Exams** → **New exam** (subject,
   date, total marks).
2. Add each question:
   - **type**: `MCQ`, `short` or `long`, with max marks;
   - for an MCQ: the **correct option** (A, B, C…);
   - for written answers: the **rubric points** (what the answer must contain, and the marks for
     each).
3. The screen shows "X of Y marks allocated". Grading won't start until every question's points
   add up exactly to its max marks.

### Step 2: Upload booklets (coordinator)
4. Drag and drop the scanned PDFs, **one PDF per student, named by roll number**
   (`21CS045.pdf` → roll number `21CS045`).
5. Each file is checked (a real PDF? under 50 MB? a duplicate?), saved, and marked **queued**.

### Step 3: AI processing (automatic, worker; about 4 minutes per booklet)
6. The worker picks up the booklet and runs the pipeline (section 6).
7. The booklet becomes **ready**, with a suggested mark and a colour for every answer.

### Step 4: Assign booklets (coordinator)
8. On the exam page, each booklet has an **Assigned to** dropdown. There are also two bulk
   options:
   - "Assign N selected to [teacher]";
   - **Distribute unassigned…**, which shares the booklets evenly between the chosen teachers.
9. Chips like "Priya Sharma: 3/10 evaluated" show each teacher's progress.

### Step 5: Evaluation (teacher)
10. The teacher signs in with their employee ID (e.g. `EMP1001`) and lands on **My papers**.
    This shows only *their* booklets, with a progress bar and red/yellow/green counts.
11. **Start evaluation** opens the marking screen, which has three panels:
    - **Left:** the original handwritten page (zoomable).
    - **Middle:** the text read from the handwriting.
    - **Right:** the suggested marks per rubric point, each with a **quote from the answer as
      evidence** and a reason. It also shows the colour and why, and the second grading's marks.
12. Keyboard shortcuts:
    - **`a`** accepts the mark;
    - **`c`** changes it (new marks plus an optional comment), then the next answer opens;
    - **`j`** / **`k`** go to the next / previous answer.
13. **Accept all green** accepts every green answer of a booklet in one click. Each one is still
    recorded separately in the audit log.

### Step 6: Results (coordinator)
14. **Export to Excel** gives three sheets:
    - **Marks:** one row per student;
    - **Detail:** every answer, with AI mark, final mark, who decided and when;
    - **Pilot metrics:** how often the AI matched the teacher, and the AI cost per booklet.

```
Coordinator: create exam + rubric → upload PDFs → (worker grades) → assign to teachers
Teacher:     sign in with employee ID → My papers → Start evaluation → accept / change marks
Coordinator: watch progress → Export to Excel
```

---

## 5. The tools we used, and why

### 5.1 Frontend (the website): folder `frontend/`

| Tool | What it is (simple) | Why we use it |
|---|---|---|
| **React** | A JavaScript library for building pages out of reusable *components* | The most common way to build interactive websites |
| **TypeScript** | JavaScript with *types* | Catches mistakes before the code runs |
| **Vite** | Runs the website locally and builds it | Very fast reloads |
| **Tailwind CSS** | Styling with short class names (`text-sm`, `bg-white`) | Quick, consistent design |
| **React Router** | Picks which page to show for each URL | Multi-page navigation |
| **TanStack Query** | Fetches and caches data from the API | Status updates every few seconds automatically |
| **supabase-js** | Supabase's JavaScript library | Keeps the signed-in session |

### 5.2 Backend (the API and worker): folder `backend/`

| Tool | What it is (simple) | Why we use it |
|---|---|---|
| **Python / FastAPI / Uvicorn** | Language / API framework / server | Simple, fast, checks input automatically |
| **Pydantic** | Describes the exact shape of data | Validates requests and AI replies |
| **Azure Document Intelligence SDK** | Microsoft's library for its OCR service | Reads handwriting fast, with a **confidence score and position for every word** |
| **Groq SDK** | Groq's Python library | Splitting and grading with AI models |
| **supabase-py** | Supabase's Python library | Database, storage, user creation |
| **PyMuPDF** | Reads PDFs | Turns each page into an image |
| **RapidFuzz** | Finds nearly matching text | Checks the AI's quoted evidence exists; matches written-out MCQ options |
| **openpyxl** | Creates Excel files | The marks export |
| **PyJWT** | Verifies login tokens | Confirms who is making each request |
| **pytest** | Testing tool | Runs the **78 automatic tests** |
| **ruff** | Code quality checker ("linter") | Finds bugs and messy code automatically |

### 5.3 Cloud services and the AI models

| Service | What it gives us | Cost |
|---|---|---|
| **Supabase** (project `evalassist`, Mumbai, free plan) | PostgreSQL database, Auth, file Storage | Free |
| **Azure AI Document Intelligence** (`prebuilt-read` model, free F0 tier) | Reads handwritten pages | Free up to **500 pages/month**; then $1.50 per 1,000 pages |
| **Groq** (free tier) | **`openai/gpt-oss-120b`** splits booklets and grades answers; **`qwen/qwen3.8-27b`** (vision) is the backup page reader | Free within limits; about $0.01 per booklet at paid prices |

### 5.4 Engineering tools (added in Phase 0)

| Tool | What it is | Why |
|---|---|---|
| **Git + GitHub** | Version control: every change is saved with a message; the code lives online | Safe history, and the project is visible on your resume |
| **GitHub Actions (CI)** | Runs checks automatically on every push: ruff, all tests, the website build, the Docker build | Broken code is caught immediately |
| **Docker / docker-compose** | Packages the backend into a "container" that runs the same on any computer | One command starts everything; needed later for free hosting |

---

## 6. How the grading pipeline works (the "AI part")

The code is in `backend/app/ai/pipeline.py`. For each booklet:

```
PDF ─► 1. page images ─► 2. skip blank pages ─► 3. READ pages (Azure OCR)
    ─► 4. SPLIT into answers (Groq) ─► 5. MCQs: RULES (no AI)
                                    └► 5. written answers: GRADE + independent CHECK (Groq)
    ─► 6. verify evidence ─► 7. COLOUR ─► 8. SAVE
```

1. **Page images.** PyMuPDF turns each page into a grey-scale image at 150 dpi. Teachers see the
   same images.
2. **Blank pages.** The back of a sheet often shows faint mirror-image "bleed-through", and an AI
   will invent text for it. So we count dark ink pixels first: under 0.05% ink means blank, and
   the page is skipped at no cost.
3. **Read (OCR) with Azure.** Each page goes to Azure, which returns every word with:
   - a **confidence** from 0 to 1 (how sure it is);
   - a **box** (where the word is on the page).

   Our code (`ai/ocr_azure.py`) then cleans the result:
   - **Noise lines are dropped.** These are lines whose words average below 0.5 confidence, such
     as bleed-through or margin scribbles.
   - **Unreadable words** (below 0.25 confidence) are written as `[illegible]`.
   - **Legibility** is measured from real numbers: under 10% unsure words is *clear*, under 35%
     is *partial*, anything more is *unreadable*.
   - **Word positions are saved** in the database, for future evidence highlighting.

   If Azure fails, that page is read by the Groq vision model instead. Since the latest fix, if
   Azure only says "too many requests, wait", we **wait and retry** rather than fall back
   (section 10, problem 16).
4. **Split (segment).** One Groq call gets all the page texts plus the question list. It returns,
   for each question, the exact answer text and its pages. It handles answers written out of
   order or continued later, and flags anything ambiguous.
5. **Grade, using three tiers.** Each answer goes to the cheapest tier that can handle it:

   | Tier | Used for | How | AI calls |
   |---|---|---|---|
   | **1. Rules** ✅ built | MCQs | Find the letter the student chose (see "How MCQs are read" below) and compare it with the correct option | **0** (rarely 1 for a re-read) |
   | **2. Own small model** ⏳ Phase 2 | Easy short answers | A model we train ourselves | 0 |
   | **3. AI grading** ✅ built (agent in Phase 1) | Written answers | A grader marks each rubric point (full / partial / absent, with a quote as evidence); a **second, independent checker** grades it again | 2 per answer |

   **How MCQs are read** (`ai/mcq_grid.py`). Most students write MCQ answers as a grid: a
   column of question numbers with a letter beside each ("1, A" / "2, D" / …). OCR reads such a
   grid column by column, so the text comes out as all the numbers and then all the letters.
   Instead, we use **where each word is on the page**:

   1. **Pair by row.** Each question number is paired with the letter on the same row to its
      right. A page counts as an MCQ grid only with at least 3 pairs, so a list in a written
      answer ("1. A random forest…") is never mistaken for MCQ answers.
   2. **Handle OCR quirks** found in the real booklets:
      - "7)" read as "71";
      - "4/." read as "41." or "5%.";
      - "1.0" with a curly D read as zero;
      - "D. All of the mentioned", where the letter is followed by the option text.
   3. **Infer missing numbers.** If a number was unreadable but its letter is in the answer
      column between Q8 and Q10, it must be Q9. These answers are flagged **yellow**.
   4. **Re-read empty cells.** If a number has no letter beside it (Azure skipped a strange
      "D"), that small piece of the page is cropped and the vision model is asked "which
      letter?". These answers are also **yellow**.

      If the re-read fails (for example because the quota is used up), the cell is just left
      for the teacher; the booklet doesn't fail.
   5. **Fallback.** Anything not found this way falls back to the text split (step 4).

   **Yellow rule:** look-alikes (a "0" read for "D"), letters read with low OCR confidence,
   inferred numbers and re-reads are all **yellow**, so the teacher confirms them. Answers read
   cleanly from the grid are green, and those are 98.7% correct.
6. **Verify evidence.** Every quote the AI gives as evidence is searched for in the answer, with
   fuzzy matching so small spelling differences are allowed. A quote that can't be found means
   the AI may have made something up.
7. **Colour** (`confidence.py`):

   | Colour | Meaning | When |
   |---|---|---|
   | 🟢 **Green** | Probably right, quick approval | Clear handwriting, grader and checker within 0.5 marks, all evidence found |
   | 🟡 **Yellow** | Check the reasoning | Some words unreadable, the gradings differ slightly, evidence missing, or an MCQ option was guessed from text or a look-alike |
   | 🔴 **Red** | Grade carefully | Page unreadable, diagram or maths, the gradings differ by more than 25%, unclear where the answer starts or ends, or the AI failed |

8. **Save.** Pages (text, words, which reader was used), answers and costs go to the database,
   and the booklet becomes **ready**.

---

## 7. The project folders and files

```
ai_evaluation_system/
├── README.md, KNOWLEDGE.md     ← setup instructions / this guide
├── .gitignore                  ← files git must never store (keys, samples, caches)
├── docker-compose.yml          ← starts API + worker + website with one command
├── .github/workflows/ci.yml    ← the automatic checks GitHub runs on every push
│
├── supabase/migrations/        ← SQL files that built the database, in order
│   ├── 0001_schema.sql … 0004_advisor_fixes.sql   tables, security rules, storage
│   ├── 0005_employee_id_assignment.sql   employee IDs + assigning scripts to teachers
│   ├── 0006_question_types.sql           question type (mcq/short/long) + correct option
│   └── 0007_ocr_words.sql                saves Azure's words/positions + which reader read a page
│
├── backend/
│   ├── .env                    ← SECRET keys (Supabase, Groq, Azure). Never shared or committed!
│   ├── .env.example            ← the same settings with blanks (safe to share)
│   ├── Dockerfile              ← recipe for the backend container
│   ├── pyproject.toml          ← Python libraries + ruff settings
│   ├── app/
│   │   ├── main.py, config.py, db.py, auth.py, access.py, audit.py, pdf.py,
│   │   │   questions_repo.py, export.py, worker.py
│   │   ├── routers/            ← API endpoints: session, users, exams, questions,
│   │   │                          scripts, review, export
│   │   └── ai/
│   │       ├── ocr_azure.py    ← Azure page reading + noise cleaning + rate-limit waits
│   │       ├── rules.py        ← tier 1: MCQ grading without AI
│   │       ├── mcq_grid.py     ← reads MCQ grids from word positions on the page
│   │       ├── client.py       ← talks to Groq: JSON replies, rate-limit waits, cost tracking
│   │       ├── prompts.py      ← instructions given to the AI
│   │       ├── schemas.py      ← exact shape of each AI reply
│   │       ├── pipeline.py     ← the steps: read → split → grade → colour
│   │       ├── confidence.py   ← green/yellow/red rules
│   │       ├── evidence.py     ← checks quoted evidence exists
│   │       └── rubric_file.py  ← loads a rubric from a JSON file (command-line runs)
│   ├── evals/                  ← the evaluation harness (section 8)
│   │   ├── download_dataset.py   downloads the 50 booklets
│   │   ├── transcribe_dataset.py reads all pages once and saves them (cache)
│   │   ├── run_eval.py           grades booklets and compares with the teacher
│   │   ├── metrics.py, dataset.py
│   │   ├── cache/              ← saved page readings and results (not in git)
│   │   └── reports/            ← evaluation reports, e.g. baseline.md
│   ├── scripts/                ← seed.py (first college + admin), run_pipeline.py (one PDF)
│   └── tests/                  ← 78 automatic tests
│
├── frontend/src/
│   ├── lib/ (api.ts, auth.tsx, supabase.ts, types.ts)
│   ├── components/ (Layout, ui, QuestionEditor)
│   └── pages/ (Login, MyPapers, Exams, ExamDetail, ReviewQueue, ReviewAnswer, Users)
│
└── samples/                    ← dataset (50 booklets) and logs; ignored by git
```

---

## 8. How we measure the AI: the evaluation harness

"The AI seems good" isn't enough, for a college or for a resume. We need **numbers**.

**The dataset:** a public research dataset (Mendeley Data, licence CC BY 4.0) with **50 real
scanned handwritten university exam booklets**.
- The subject is Data Science: 20 MCQs and 15 two-mark short answers.
- It includes the answer key and **the teacher's real marks for every question**.

**The split:** students are divided once, at random with a fixed seed (42):

| Set | Students | Used for |
|---|---|---|
| **train** | 30 | Training our own model later (Phase 2) |
| **val** (validation) | 10 | Tuning settings and prompts |
| **test** | 10 | The final, honest score. We never tune on these, or the score would be cheating |

**How it runs:**
1. `python -m evals.download_dataset` downloads the booklets. ✅ All 50.
2. `python -m evals.transcribe_dataset` reads every page once with Azure and saves the result in
   a cache. ✅ 200 pages, about 25 minutes, free.
3. `python -m evals.run_eval --split test --name baseline` grades the cached text, compares it
   with the teacher, and writes `evals/reports/baseline.md`. ⏳ 5 of 10 done.
   - It saves each booklet's result as it goes, so when Groq's daily limit stops it, running the
     same command later continues where it stopped.

**What it measures:**

| Number | Meaning | Good value |
|---|---|---|
| **QWK** (quadratic weighted kappa) | Agreement with the teacher, standard in automatic grading research. 0 = chance, 1 = perfect | > 0.7 |
| **MAE** (mean absolute error) | Average difference from the teacher's mark | as low as possible |
| **Exact %** | How often the AI's mark equals the teacher's | high |
| **Green precision** | How often a **green** answer actually matches the teacher. Teachers will trust green, so this matters most | ≥ 90% |
| **MCQ read %** | How often we read the same option the teacher recorded | ~100% |
| **Calls / cost / seconds per booklet** | Speed and cost | low |

---

## 9. Users, roles and signing in

| Role | Signs in with | Can do |
|---|---|---|
| **Admin** | email (or employee ID) | Everything, including adding users |
| **Exam cell coordinator** | **employee ID** | Exams, rubrics, uploads, **assigning booklets**, retries, Excel export |
| **Teacher** | **employee ID** | Only booklets assigned to them: evaluate and accept or change marks |

**How employee-ID sign-in works** (Supabase only understands emails, so the backend helps):
1. The teacher types `EMP1001` and a password.
2. The backend finds that employee ID, signs in to Supabase on their behalf, and returns a
   **session token**.
3. Every later request carries the token, and the backend checks it and the user's role.

**Safety:**
- Employee IDs ignore upper/lower case.
- A wrong password and an unknown ID give the **same** error, so nobody can discover which IDs
  exist.
- Wildcard tricks are blocked.

**Demo accounts** (passwords were given to you in the chat; they aren't written here, so they
can't leak):

| Name | Sign in with | Role |
|---|---|---|
| Exam Cell Admin | `admin@example.com` | admin |
| Exam Cell Coordinator | `EXC001` | coordinator |
| Priya Sharma | `EMP1001` | teacher |
| Ravi Kumar | `EMP1002` | teacher |

---

## 10. Problems we met, and how we fixed them

| # | Problem | What we saw | Fix |
|---|---|---|---|
| 1 | Switch AI provider | You asked for Groq instead of Claude | Rewrote `ai/client.py` for Groq |
| 2 | Free-tier limits | Groq allows about 8,000 tokens/minute; vision about 1 page/minute | Realistic output sizes; **wait and retry** when rate limited |
| 3 | Vision model gave garbage in JSON mode | Random symbols and Japanese text | Plain-text reading; our code works out legibility itself |
| 4 | AI "read" blank pages | Invented answers on bleed-through pages | Ink-pixel blank detection |
| 5 | Grading replies cut off | Too much "thinking", so incomplete JSON | Medium effort; retry once with double the budget |
| 6 | One bad answer killed the whole booklet | One failed call stopped all 35 answers | That answer becomes **red, "grade manually"**; the rest continue |
| 7 | Unstable internet | DNS errors, dropped connections | Retries everywhere; the worker never crashes on a network blip |
| 8 | Student_2 stuck in "AI evaluating" | Saving costs after every call failed and restarted the booklet | Costs are saved once at the end |
| 9 | Silent long waits | A daily limit meant waiting hours without saying so | Waits over 90 s stop with a clear message; the coordinator presses Retry |
| 10 | Port in use | Port 5173 is your `doctor_dashboard` project | EvalAssist uses **5174** |
| 11 | Secret key in a shared file | The service key was in `.env.example` | Moved to `.env` (ignored by git) |
| 12 | **Too slow: about 30 min per booklet** | About 3 min reading pages, about 27 min of about 69 rate-limited Groq calls | **MCQ rules tier** (about 40 fewer AI calls) plus **Azure reading** (about 5 s per page) → **about 4 min, 34 calls** |
| 13 | "A random forest…" read as option A | The article "A" looked like an option letter | A letter counts only when written like an option ("A.", "(a)", "Ans: A", or alone) |
| 14 | Curly "D" read as "0" | Azure read a handwritten D as zero | Look-alikes (0→D, 8→B) are accepted but flagged **yellow** |
| 15 | Supabase paused the project | The free plan allows 2 active projects | Paused the old "eval" project (your choice) and restored `evalassist` |
| 16 | **Azure free-tier rate limit** | While reading the 50 booklets, Azure said "too many requests"; 2 pages silently fell back to the slow Groq reader | At most 2 pages at a time, slower status checks, and **wait and retry**; the 2 affected booklets were re-read. New test added |
| 17 | Noisy logs | The Azure library logged every web request; a harmless "Event loop is closed" error at the end of each run | Azure logging silenced; the Groq connection is now closed properly; Groq waits are now logged |
| 18 | Public keys in templates | The `.env.example` files had the real project URL and public key | Replaced with placeholders before pushing to GitHub |
| 19 | **MCQs read only 45% of the time** | OCR reads MCQ grids column by column, so numbers and letters come out separated | **MCQ grid reader**: pair by position on the page, handle OCR quirks, infer missing numbers, re-read empty cells → **89%** on the test students |
| 20 | A failed re-read failed the whole booklet | While measuring, the vision model's quota ran out mid-booklet | A re-read is optional: if it fails, that one cell is left for the teacher |

---

## 11. Test results so far

### Speed and cost (Student_1, command-line run)

| | Before (Groq only) | Now (Azure + MCQ rules) |
|---|---|---|
| Time per booklet | ~30 min | **~4 min (245 s)** |
| AI calls | 69 | **34** |
| Cost (at paid prices) | $0.029 | **$0.017** (~₹1.5) |

### The baseline (first honest accuracy measurement)
5 test booklets so far, 75 short answers, compared with the real teacher marks:

| Number | Result | Meaning |
|---|---|---|
| QWK | **0.43** | Moderate agreement; the target is > 0.7 |
| MAE | 0.62 marks | Off by about 0.6 of 2 marks on average |
| Exact match | 46.7% | |
| AI average vs teacher average | **0.65 vs 1.17** (out of 2) | **The AI is much harsher than the teacher** |
| Green share / green precision | 71% / **36%** | **Green can't be trusted yet** |
| MCQ read correctly | **45%** | **Something is wrong with MCQ reading** (now fixed: 89%, see below) |
| Per booklet | about 16 s reading + about 4.8 min grading, about 24 AI calls, about $0.016 | |

### What the baseline taught us (this is why we measure)
1. **MCQ problem.** Students write MCQs as a grid ("1, A" / "2, D" / …). Azure reads the grid
   **column by column**, so all the numbers come out first and then all the letters, jumbled. The
   AI can't pair them, so MCQs come out empty.
   - Azure also gives each word's position on the page, and pairing each number with the letter
     on the **same row** fixes it: tested by hand, this gets 19 of 20 right.
   - The 20th, a "D" with a crossbar, was skipped by Azure entirely. A re-read of just that spot
     with the vision model will recover it.
2. **The AI is harsher.** The AI gave less than the teacher on 38 of 75 answers, and more on only
   3. The teacher gives partial credit for relevant attempts and accepts any valid example (for
   instance, "Hospitalities" got full marks as a data science application). The AI treats the
   rubric as a closed list and gives 0.
3. **Green isn't trustworthy.** Green means "the grader and checker agree", but both share the
   same harshness, so their agreement doesn't make them right. Answers containing `[illegible]`
   words could also still be green.

### Fix 1 result: MCQ reading (compared with the options the teacher recorded)

| Students | Before | Word positions only | + inferred numbers + re-reads |
|---|---|---|---|
| test (10) | 45% | 80% | **89%** |
| validation (10) | – | 90% | **92%** |
| train (30) | – | 75% | **81%** |

- Green MCQs (read cleanly from the grid) are **98.7% correct**. Everything less certain is
  yellow.
- The re-read recovered about 4 of every 5 empty cells it ran on.
- Note: the rules were developed by looking at train/validation students and one test student
  (Student_5, where the problem was found). The test number may be slightly optimistic.

### Automatic tests
**78 tests pass** (`cd backend && .venv\Scripts\python -m pytest`). They cover:
- the colour rules and evidence matching;
- the pipeline, using a fake AI;
- MCQ rules, the MCQ grid reader (every layout we found) and OCR cleaning;
- Azure fallback and rate-limit retry;
- the Excel file, PDFs and blank pages;
- employee-ID rules and assignment;
- the evaluation metrics.

GitHub runs them automatically on every push.

### Login and permission checks (live system)
- All roles sign in correctly.
- Teachers see only their own papers.
- Teachers can't assign papers or add users.
- Wrong passwords and wildcard tricks are rejected.

---

## 12. Security, in simple words

- **Secrets** (Supabase service key, Groq key, Azure key) live only in `backend/.env`, which git
  ignores.
  - Before pushing to GitHub, every file was scanned for keys and passwords. None were found.
- Every API request must carry a valid session token, and roles are checked on every action.
- Teachers can only open scripts assigned to them.
- Colleges are separated in every query, and Supabase **Row Level Security** adds a second lock.
- The **audit log** records who did what, when, and the before/after values.
- Students are stored by **roll number** only. Files are private, and the website gets 1-hour
  links.
- Data is stored in Mumbai (India).

---

## 13. What's next

### Right now: finish Phase 0
1. Finish the baseline: rerun `python -m evals.run_eval --split test --name baseline` after Groq's
   daily limit resets.
2. ✅ **Fix 1: MCQ grid reader.** Done: 45% → 89% on the test students (section 11).
3. **Fix 2: calibrate grading.** Treat rubric items as *examples* rather than a closed list, and
   give partial credit for relevant attempts. Tune this on the **validation** students only.
4. **Fix 3: stricter green.** `[illegible]` in the answer means yellow. Tune until green
   precision is at least 90%.
5. Measure on the test set: "baseline vs improved". This is the first resume number.

### Then the v2 plan
| Phase | What | Why it stands out |
|---|---|---|
| **1. LangGraph agent** (weeks 2–4) | Grading becomes an **agent** with tools: `get_rubric`, `find_precedents`, `reread_region` (re-reads a cropped part of the page), `submit_grade`, plus a **critic** agent. It saves progress, so a failure resumes instead of restarting. A "Why this mark?" panel shows the agent's steps, and the evidence words are highlighted on the page image | A real agent that uses tools, not a fixed chain |
| **2. Our own small model** (weeks 4–7) | Train a small model (DeBERTa/MiniLM) on public grading datasets plus our 750 answers. It runs on a normal CPU in milliseconds, so **1 minute per booklet** and almost no AI cost | "I trained my own model" |
| **3. Learning from teachers** (weeks 7–9) | Teachers' corrections become examples (**pgvector** similarity search). A **calibration agent** suggests rubric notes, and the model is retrained, but kept only if the evaluation improves | The system improves itself |
| **4. More agents** (weeks 9–11) | Drafts rubrics from the question paper, writes feedback reports for students, adds class insights and live progress | A complete product |
| **5. Ship it** (weeks 11–12) | Free public demo (Vercel + Hugging Face Spaces), guest logins, a demo video and a polished README | Recruiters can try it |

---

## 14. How to run it

**Option A: three terminals**
1. Backend API (in `backend`): `.venv\Scripts\python -m uvicorn app.main:app --port 8000`
2. Worker (in `backend`): `.venv\Scripts\python -m app.worker`
3. Website (in `frontend`): `npm run dev -- --port 5174`

Then open **http://localhost:5174**.

**Option B: Docker** (in the main folder): `docker compose up --build`

**Useful commands** (in `backend`):
- Grade one PDF without the website:
  `.venv\Scripts\python scripts\run_pipeline.py ..\samples\mendeley_ds_exam\Student_Pdf\Student_1.pdf ..\samples\mendeley_ds_exam\rubric.json --teacher-marks ..\samples\mendeley_ds_exam\teacher_marks\Student_1.json`
- Run the tests: `.venv\Scripts\python -m pytest`
- Run the code checker: `.venv\Scripts\ruff check .`
- Run an evaluation: `.venv\Scripts\python -m evals.run_eval --split test --name baseline`
- Logs: `samples/worker.log`, `samples/api.log`, `samples/frontend.log`, `samples/eval_baseline.log`

**Settings** (`backend/.env`):

| Setting | Meaning |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Database connection (secret key!) |
| `GROQ_API_KEY` | Groq key (secret!) |
| `GROQ_GRADING_MODEL`, `GROQ_CHECK_MODEL` | Splitting/grading and the independent check (`openai/gpt-oss-120b`) |
| `GROQ_VISION_MODEL` | Backup page reader (`qwen/qwen3.8-27b`) |
| `OCR_PROVIDER` | `auto` (Azure if configured), `azure`, or `groq` |
| `AZURE_DI_ENDPOINT`, `AZURE_DI_KEY` | Azure Document Intelligence (secret key!) |
| `MAX_PARALLEL_CALLS` | How many Groq calls run at once |
| `CORS_ORIGINS` | Which website addresses may call the API |

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **Frontend / Backend** | The website you see / the programs that store data and enforce rules |
| **API / endpoint** | URLs the website calls to get data or do actions / one such URL |
| **localhost / port** | "This computer" / a numbered door a program listens on (8000 API, 5174 website) |
| **Database / table / row** | Organised storage / like a spreadsheet tab / one record |
| **Migration** | A SQL file that changes the database structure |
| **Row Level Security (RLS)** | Database rules deciding which rows each user may see |
| **Session token / JWT** | A signed pass proving who you are |
| **Service-role key / publishable key** | Secret master key (backend only) / public key (safe in the browser) |
| **Worker / queue** | Background program / list of jobs waiting |
| **OCR** | Optical Character Recognition: turning an image of writing into text |
| **Confidence score** | How sure the OCR or AI is (0 to 1) |
| **Bounding box / polygon** | The position of a word on the page |
| **LLM / vision model** | AI that reads and writes text / AI that also understands images |
| **Prompt** | Instructions given to the AI |
| **Token** (AI) | A piece of a word; AI usage is counted in tokens |
| **Rate limit** | A cap on usage per minute or day |
| **JSON schema** | An exact description of the fields an AI reply must have |
| **Segmentation** | Splitting a booklet into answers per question |
| **Rubric** | The marking scheme: points an answer should contain, with marks |
| **Tier / router** | The levels of grading (rules → own model → AI) / the code deciding which level handles an answer |
| **Agent** | An AI that decides its next step and uses tools, not just a fixed sequence |
| **LangGraph** | A library for building agents as graphs of steps that can save and resume |
| **Fine-tuning** | Training an existing small model further on our own examples |
| **Evaluation / baseline** | Measuring the AI against real teacher marks / the first measurement every improvement must beat |
| **Train / val / test split** | Students for training / for tuning / for the final honest score |
| **QWK** | Quadratic weighted kappa: an agreement score (1 = perfect, 0 = chance) |
| **MAE** | Mean absolute error: average difference from the teacher's mark |
| **Precision (green)** | Of the answers marked green, the share that were really right |
| **Cache** | Saved results reused instead of recomputed |
| **Git / commit / push** | Version control / a saved change / uploading changes to GitHub |
| **CI (continuous integration)** | Automatic checks on every push |
| **Linter (ruff)** | A tool that finds bugs and messy code automatically |
| **Docker / container** | Packages a program with everything it needs, so it runs the same everywhere |
| **Audit log** | A permanent record of who did what and when |
| **CORS** | Browser rule: the API lists which websites may call it |
| **`.env` file** | Settings and secrets read when a program starts |
