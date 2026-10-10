# EvalAssist

EvalAssist helps teachers evaluate handwritten answer scripts faster. The AI reads each booklet, splits it into answers, and suggests marks against the college's rubric. It gives a reason for every mark and a green, yellow or red confidence flag. The teacher accepts or changes each mark, and every decision is saved to an audit log and exported to Excel.

```
frontend/   React + Vite + Tailwind. The teacher/coordinator website.
backend/    FastAPI API + background worker running the AI grading agent (Groq API).
supabase/   SQL migrations (already applied to the "evalassist" project, ap-south-1).
```

## How the AI grading works (`backend/app/ai/`)

The agent runs on the **Groq API** using three configurable models:
- **Vision model** (`GROQ_VISION_MODEL`, default `qwen/qwen3.8-27b`) reads the handwriting.
- **Grading model** (`GROQ_GRADING_MODEL`, default `openai/gpt-oss-120b`) splits the booklet and grades.
- **Check model** (`GROQ_CHECK_MODEL`, default `openai/gpt-oss-120b`) does the independent second grading.

Every call uses Groq's strict JSON-schema output, and the reply is validated before use.

1. **Read.** Each scanned page is rendered to an image and sent to the vision model, which transcribes it. It also reports legibility, the question labels on the page, and whether the page has diagrams or maths.
2. **Segment.** One text-only call to the grading model splits the booklet into answers per question. It handles answers written out of order and answers that continue on another page.
3. **Grade.** The grading model marks each rubric point with a verdict, the marks, a verbatim evidence quote and a one-line reason. The code then clamps every mark to the rubric's limits.
4. **Double-check.** A second, stricter "checker" grades the answer independently. Setting `GROQ_CHECK_MODEL` to a different model makes this check more independent. The code also confirms that every evidence quote really appears in the answer text.
5. **Decide the colour** (`confidence.py`):
   - **Green:** clear handwriting, the two gradings agree within 0.5 marks, and all evidence is verified.
   - **Yellow:** a few words are unreadable, the gradings differ slightly, or an evidence quote wasn't found.
   - **Red:** a page is unreadable, the gradings differ by more than 25% of the marks, the answer has a diagram or maths, or it's unclear where the answer starts and ends.

The token usage and estimated cost of every AI call is saved in `ai_calls`. Prices are set in `MODEL_PRICES` in `backend/app/config.py`; add a line there if you switch to a model not listed. The Excel export includes a **Pilot metrics** sheet: how often the AI mark was accepted unchanged, the mean difference from teacher marks, the colour mix, and the average cost per script.

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows (source .venv/bin/activate on Mac/Linux)
pip install -e ".[dev]"
copy .env.example .env            # then fill in the two keys below
```

In `backend/.env`:
- `SUPABASE_SERVICE_ROLE_KEY`: in the Supabase dashboard, go to **evalassist**, then **Project Settings**, then **API Keys**, and copy the service_role / secret key. Keep it on the server only.
- `GROQ_API_KEY`: your Groq API key, from https://console.groq.com/keys.
- `GROQ_VISION_MODEL`, `GROQ_GRADING_MODEL`, `GROQ_CHECK_MODEL`: the models to use. The defaults are listed above. Any replacement must support strict JSON-schema output on Groq, and the vision model must accept images. `qwen/qwen3.8-27b` is a preview model on Groq, so check the [models page](https://console.groq.com/docs/models) if it stops working.

Create your college and the first admin account:
```bash
python scripts/seed.py --college "Your College" --email admin@college.edu --name "Exam Cell" --password "a-strong-password"
```

Run the API and the worker in two terminals:
```bash
uvicorn app.main:app --reload --port 8000
python -m app.worker
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173
```
`frontend/.env` already points to the Supabase project and to `http://localhost:8000`.

## Using it

**Admin / exam coordinator**
1. Sign in with your email. On the **Users** page, add teachers with an **employee ID** and a temporary password (email is optional for teachers).
2. **New exam:** subject, date, total marks. Add each question with its rubric points; they must add up to the question's max marks.
3. Upload the scanned PDF booklets, **one PDF per student, named by roll number** (e.g. `21CS045.pdf`). The worker reads and grades them automatically.
4. Assign scripts to teachers on the exam page: pick a teacher per script, or **Distribute evenly among teachers** for all unassigned scripts.
5. **Export to Excel** when evaluation is done.

**Teacher**
1. Sign in with your **employee ID** and password.
2. **My papers** lists the scripts assigned to you, grouped by exam, with progress. Click **Start evaluation** (or **Continue**).
3. For each answer: original handwriting, the AI's reading, and per-rubric-point marks with evidence and a green/yellow/red flag. `a` accept, `c` change, `j`/`k` next/previous. After the last answer you're taken back to My papers.

Teachers can only see and mark scripts assigned to them; the API enforces this.

## Test the AI on real scripts before a pilot

This runs the full grading agent on one PDF without the website or database, and prints the marks, colours and cost:

```bash
cd backend
python scripts/run_pipeline.py path/to/21CS045.pdf scripts/sample_rubric.json --teacher-marks marks.json --out result.json
```
`marks.json` holds the teacher's marks, for example `{"1": 3.5, "2": 2}`. With it, the script also prints agreement with the teacher. Run it on 3–5 booklets a teacher has already marked to measure accuracy and real cost per script.

## Tests

```bash
cd backend && pytest
```

## Security notes

- The browser only uses Supabase for sign-in. All data goes through the API, which checks the user's role and college on every request.
- Row level security is enabled on every table. A signed-in user can only read their own college's rows, and the `ai_calls` cost table is not readable by the browser at all.
- Scanned scripts are stored in a private bucket. Page images are served through signed links that expire after 1 hour.
- Students are identified by roll number only.
