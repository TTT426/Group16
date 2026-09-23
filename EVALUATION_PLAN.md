# Draft Evaluation Plan

## Problem Grounding

### Target Persona

Undergraduate student team leaders working on collaborative software
engineering projects in teams of four.

### Current Problem

Teams currently coordinate pull-request reviews and task handoffs through
fragmented LINE or Discord messages. Team leaders must manually ask members for
progress, identify stale branches, and reconcile conflicting spreadsheet
records.

### Observable Change

If the proposed tool works:

- Teams will complete task handoffs and PR reviews faster.
- Fewer reminder messages will be required.
- Participants will correctly identify the current task owner and blocker.
- Review blockers will be identified without help from the test facilitator.

## Evaluation Plan

### Success Definition and Human–AI Boundary

The primary success metric is coordination turnaround time: the time from when
a mock pull request is declared ready for review until the team correctly
identifies the reviewer, blocker, and next action.

Each team will first complete a baseline workflow using its current
LINE/Discord and spreadsheet process. The same team will then complete an
equivalent workflow using the prototype. The tasks will contain different but
comparable names and blockers.

The percentage improvement will be calculated as:

`(baseline median time - prototype median time) / baseline median time * 100`

The prototype will be considered successful if the median coordination
turnaround time is at least 30% lower than the baseline.

AI acts only as an assistive summarizer or recommender. Humans retain authority
over reviewer assignment, approval, merge, and all other repository actions.

### Target Users

We will recruit two or three student project teams from department courses.
Each team should contain approximately four members and have previous
experience using GitHub pull requests for a group project.

### Method

1. Give each team a simulated pull-request scenario containing an assigned
   reviewer, a stale branch, and one unresolved blocker.
2. Ask the team to resolve the scenario using its normal communication process.
3. Record completion time, number of reminder messages, incorrect assignments,
   and requests for facilitator help.
4. Give the team an equivalent scenario using the prototype.
5. Record the same measurements.
6. Conduct a five-minute semi-structured interview after both scenarios.
7. Ask each participant to rate the statement “I could clearly identify the
   task owner, blocker, and next action” on a five-point scale.

To reduce practice effects, scenario details will differ between the baseline
and prototype tasks. If more than two teams participate, half will use the
prototype first and half will use the existing process first.

### Minimum Evidence Threshold

We will not claim preliminary success unless:

- At least two teams, with at least eight participants total, complete both
  workflows.
- Every team completes the prototype workflow without facilitator
  intervention.
- Prototype median coordination time is at least 30% lower than baseline
  median time.
- At least six of eight participants rate task context clarity as 4 or 5 out
  of 5.
- No critical failure causes an incorrect merge or loss of task information.

If any threshold is missed, we will report the result as inconclusive or
unsuccessful and document the observed failure rather than changing the
threshold after testing.
