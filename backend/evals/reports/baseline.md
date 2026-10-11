# Evaluation: baseline

- Split: **test** (5 booklets) · 2026-10-10T11:00:08+00:00
- Models: vision `azure/prebuilt-read`, grading `openai/gpt-oss-120b`, check `openai/gpt-oss-120b`

## Short answers vs teacher (Q21–35)
| Answers | QWK | MAE | Exact | Within 0.5 | AI mean | Teacher mean |
|---|---|---|---|---|---|---|
| 75 | 0.427 | 0.62 | 46.7% | 60.0% | 0.647 | 1.173 |

## Confidence colours (short answers)
| Colour | Share | AI = teacher |
|---|---|---|
| green | 70.7% | 35.8% |
| yellow | 22.7% | 82.4% |
| red | 6.7% | 40.0% |

## MCQs (Q1–20)
AI read the same option as the teacher recorded: **45.0%**

## Cost and speed per booklet
| Stage | AI calls | Tokens | Cost (USD) | Seconds |
|---|---|---|---|---|
| reading | 3.4 | 0 | 0.0051 | 16.2 |
| grading | 24.2 | 29750 | 0.01071 | 290.5 |
