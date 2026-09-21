# Draft Evaluation Plan

## Problem Grounding
1. **Target Persona:** Undergraduate student team leaders working on collaborative software engineering projects with 4 team members.
2. **Current Workaround:** They currently rely on fragmented communication across LINE/Discord channels, manually chase members for PR progress, and reconcile merge conflicts reactively over spreadsheet logs.
3. **Observable Change:** PR review bottlenecks and stale branches will decrease observably; handoff blockers will be resolved within 24 hours without manual follow-up reminders.

## Evaluation Plan Draft
* **Success Definition & Human-AI Boundary:** We will know our tool works if team members can complete task handoffs and PR reviews with at least a 30% reduction in coordination turnaround time. *(Human-AI Boundary: Human-in-the-loop — AI acts purely as an assistive summarizer/recommender; humans retain full approval authority over all repository actions).*
* **Target Users:** 2–3 student project teams in our department courses; accessed through direct peer outreach and lab session recruiting.
* **Method:** Structured observation of a simulated 20-minute pull request workflow, followed by a 5-minute semi-structured interview.
* **Minimum Evidence Threshold:** At least 2 teams independently complete a mock merge workflow using our tool without external intervention and confirm in the interview that task context was clear.