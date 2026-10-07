# ARCHITECTURE_AUDIT

> This document records the pre-deployment architecture that was audited. The follow-up implementation now runs scheduled automation through GitHub Actions and uses Ollama only for AI requests. See the GitHub setup instructions in [README.md](./README.md).

## Current Architecture

The existing Campus Copilot project is a lightweight Python automation system built around a daily operational loop rather than a full product platform. It is best understood as a personal AI assistant focused on three primary outputs: academic reminders, job discovery, and scheduled communication.

### Components

1. CLI entry and command orchestration
   - `campus_copilot/__main__.py` starts the app.
   - `campus_copilot/main.py` defines the command surface (`run`, `classroom`, `jobs`, `remind`, `ask`, `study`, `pa`, `feedback`).
   - This gives the project a useful terminal-first interface without a web app or dashboard.

2. Orchestration layer
   - `campus_copilot/pipeline.py` is the workflow coordinator.
   - It collects classroom data, fetches jobs, runs LLM-powered summarization, and broadcasts updates.
   - `run_daily()` aggregates the classroom and job sections into a single daily brief.

3. LLM layer
   - `campus_copilot/llm.py` wraps two AI tiers:
     - Hermes (local model via Ollama) for fast, low-cost drafting.
     - Claude (Anthropic) for higher-quality auditing and final refinement.
   - Budget logic (`MAX_CLAUDE_CALLS_PER_DAY`) protects cost and usage.

4. Data and storage layer
   - `campus_copilot/store.py` uses SQLite for:
     - dedupe tracking (`seen`)
     - job feedback (`feedback`)
     - Claude daily usage (`usage`)
     - job metadata (`job_meta`)
   - This is currently a small memory database rather than a full product datastore.

5. Integrations
   - Google Classroom and Google Calendar via the Google API.
   - Email fallback using IMAP for locked-down college accounts.
   - Public job APIs: Greenhouse, Lever, Remotive.
   - Delivery channels: Telegram, WhatsApp (Twilio), email, Notion, calendar.

6. Notification layer
   - `campus_copilot/notify.py` centralizes outbound communications.
   - It tries each configured channel individually and does not let one failure block the entire run.

7. Academic and career data sources
   - `campus_copilot/classroom.py` fetches assignments, announcements, and course materials.
   - `campus_copilot/jobs.py` fetches new jobs and filters them by title.

8. Configuration and prompts
   - `config.yaml` defines timezone, profile, job sources, and classroom timing.
   - `prompts/*.md` define model system prompts and specialist prompts.
   - `.env.example` lists the environment variables required by integrations.

### Data flow

The dominant flow is:

1. Config loads from `config.yaml` and environment variables.
2. `pipeline.py` calls classroom and job fetchers.
3. Data is normalized into a simple JSON structure.
4. Hermes drafts a summary or ranking.
5. Claude audits the output against raw data when available.
6. The final text is broadcast to Telegram, email, WhatsApp, Notion, and/or Google Calendar.
7. SQLite stores seen items, feedback, and Claude budget usage.

### Storage

Storage is intentionally lightweight:

- SQLite file: `data/copilot.db`
- Small persisted state for deduplication and learning.
- No formal relational model for academic life, deadlines, subject progress, projects, internship applications, or studies.
- No user-specific history beyond job feedback and seen records.

### AI layer

The project uses a very practical AI stack:

- Local model: Hermes via Ollama for cheap/high-volume tasks.
- Remote model: Claude via Anthropic for strategic auditing and synthesis.
- LLM decisions are used for summarization, job scoring, and assistant questions.

### CLI / UI

The app is terminal-first. There is no web dashboard, no task manager, and no user workspace. The project is designed as a daily automation “operating system” that speaks through notifications rather than an interactive UI.

### Configuration

The configuration model is simple but not yet product-grade:

- timezone
- degree + graduation year + skills
- allowed job keywords and exclusions
- data sources and lookback windows

This is a useful start, but it does not yet represent a full academic, project, and career state model.

### Automation

The system already has a strong automation mindset:

- daily run
- reminder loop
- job tracking
- AI-driven summaries
- broadcast notifications

This is a capable personal assistant pattern for a student, but it remains a workflow script layer, not a complete decision engine.

---

## Current Strengths

1. Clear product thesis
   - The project is driven by a real-world problem: helping a student manage academic and career priorities without cognitive overload.

2. Useful automation architecture
   - It already connects major verticals: classroom, jobs, LLM, notifications, and reminders.

3. Good fallback strategy
   - Classroom API fails gracefully to IMAP fallback.
   - Claude can be unavailable while the system still ships a draft.
   - Notification channels can fail independently without taking down the run.

4. Low-complexity implementation
   - Python + SQLite + YAML + basic CLI is easy to run and operate on a laptop.
   - This is a pragmatic architecture for a student workload.

5. Learning loop
   - Job feedback is stored and reused to improve future ranking.
   - This is a good start toward personalized prioritization.

6. Honest cost-control model
   - The Claude budget and local-model-first approach show attention to realistic constraints.

7. Good integration choices
   - It avoids brittle scraping and prefers public APIs, which makes it more maintainable than a web-scraping pipeline.

---

## Current Problems

1. No true priority engine
   - The project does not yet model tasks as a full rankable system with deadlines, effort, impact, dependencies, and exam proximity.
   - It lacks a single “what should I do now?” decision engine.

2. Academic model is too thin
   - The app can fetch assignments but cannot maintain a complete academic operating model.
   - It does not track semesters, marks, GPA, revision status, topics, weak areas, or learning velocity.

3. Job workflow is narrow
   - Jobs are scored, but there is no structured application pipeline, interview tracker, networking board, or opportunity lifecycle state.

4. No unified task graph
   - There is no canonical structure for assignments, project tasks, study tasks, internships, and personal tasks.
   - Without that, priority ranking is fragile and ad hoc.

5. Storage is not yet a product database
   - SQLite is useful, but the schema is simple enough to be a memory store rather than a real system of record.
   - There are no strong models for academic records, study history, project milestones, or opportunity tracking.

6. Architecture is more script-oriented than system-oriented
   - It works best as a batch automation utility, not as a rich personal operating system.
   - There is no persistent user workspace, no dashboard, and no long-term reasoning engine.

7. Security and configuration risk
   - Secrets are stored in `.env` and `secrets/` files.
   - The project requires a careful secret-management strategy before being used seriously.
   - One real issue already visible in the code is a broken Notion auth header pattern in `notify.py`, which must be fixed to use the actual token properly.

8. No robust testing or validation strategy
   - The project has no automated tests, contract checks, or integration validation around API responses and data parsing.

9. Missing UX for long-term planning
   - There is no “today plan”, “this week”, “later” hierarchy or explanation layer that ties a recommendation to rationale, effort, and impact.

10. No project and career portfolio layer
   - There is no system for tracking GitHub projects, skills, milestones, certificates, or internship readiness stages.

---

## Missing Capabilities

To become the full Campus Copilot described in the product brief, the project needs the following capabilities:

1. Priority Engine
   - A centralized prioritization model that ranks all tasks by:
     - deadline urgency
     - academic weight
     - career impact
     - effort required
     - dependency chains
     - skill-building value
     - overdue or stuck state
     - user-defined importance
   - Output types: NOW, NEXT, TODAY, THIS WEEK, LATER.

2. Academic lifecycle tracking
   - University, semester, subjects, units, topics, assignments, labs, exams, attendance, marks, and revision states.
   - Student-specific KPIs and tracking for weak topics and learning gaps.

3. Personal productivity layer
   - Focus blocks, Pomodoro sessions, time estimation, study cadence, and weekly planning.
   - Integration with calendar and to-do lists.

4. Career and opportunity management
   - Internship and job pipeline with stages, deadline tracking, and application follow-up.
   - Resume/portfolio readiness checks.
   - Interview preparation tracking.

5. Project and skill portfolio
   - GitHub/project tracking, skill graphs, proof of work, and roadmap evolution.
   - Recommendations for what to build next based on career target.

6. Memory and contextual AI model
   - A persistent memory layer that remembers semester status, deadlines, opportunities, notes, and user preferences.
   - This should move beyond the current simple “seen jobs” database.

7. Visual dashboard and UX
   - A web dashboard or local app is needed for real-time insight.
   - Human-readable summaries should be easier to use than a terminal output alone.

8. Data quality and governance
   - Schema validation, consistent IDs, source normalization, and tracking for data provenance.

9. Reliability and testing
   - Unit tests for parsing, ranking, and notification behavior.
   - End-to-end smoke tests for daily run and reminder flows.

---

## Proposed Architecture

A safer and more scalable architecture is a layered system built around a persistent “student state” model.

### 1. Presentation Layer

- CLI for automation and scripts.
- Optional web dashboard or local desktop app.
- Notification delivery layer for Telegram/Email/WhatsApp/Notion/Calendar.

### 2. Application Services

- Priority Engine service
- Academic manager
- Job and internship manager
- Study planner
- Project and portfolio tracker
- Notification orchestrator
- Daily brief generator

### 3. Domain Models

The system should center on a few core entities:

- StudentProfile
- Subject
- Topic
- Assignment
- Exam
- Task
- Opportunity
- Project
- Skill
- Goal
- StudySession

These domain objects should be persisted in a robust relational or document store rather than being implied by ad hoc JSON blobs.

### 4. Integration Adapters

- Google Classroom
- Google Calendar
- IMAP email fallback
- Greenhouse / Lever / Remotive APIs
- LLM providers (Hermes/Ollama + Claude)
- Notion / Telegram / WhatsApp / SMTP

### 5. Memory and Retrieval Layer

- Structured relational data for academic and career state.
- Optional vector or search layer for notes and unstructured observations.
- A feedback mechanism for ranking personalization.

### 6. Decision Layer

The Priority Engine should not just sequence tasks; it should explain reasoning.

Example outputs:

- NOW: finish DBMS normalization assignment
- NEXT: revise DSA recursion
- TODAY: apply to internship X
- THIS WEEK: complete two core concepts and one project milestone

This should include rationale based on impact and urgency.

---

## Migration Plan

The migration should be incremental and should not discard the existing project’s strengths.

### Phase 0 — Stabilize the base system

- Fix broken or risky integrations.
- Normalize config and environment handling.
- Add automated smoke tests for current commands.
- Add schema validation for data returned by Classroom and job APIs.

### Phase 1 — Add a real data model

- Introduce a robust entity model for:
  - student profile
  - subjects and topics
  - exams and assignments
  - tasks and priorities
  - projects and skills
- Move data from ad hoc JSON and SQLite-only memory to a more explicit persistent schema.

### Phase 2 — Build the Priority Engine

- Define task scoring inputs and formulas.
- Add a canonical task list with statuses, effort, and dependency links.
- Produce view states: NOW, NEXT, TODAY, THIS WEEK, LATER.
- Add “why this now?” reasoning output.

### Phase 3 — Extend the academic model

- Capture semester structure, course plan, weak topics, revision states, and marks.
- Add attendance and study tracking.
- Link tasks back to academic outcomes and milestones.

### Phase 4 — Add career and opportunity pipeline

- Track applications, resume readiness, interview prep, and follow-up tasks.
- Score opportunities by alignment to student goals.

### Phase 5 — UX and product layer

- Add dashboard views.
- Add a local web app or stronger CLI dashboard.
- Connect all modules to a unified personal operating model.

### Phase 6 — Hardening and scale

- Add production security safeguards.
- Separate secret management from app code.
- Add improved observability, telemetry, and resilience.

---

## Recommendation

The existing Campus Copilot is a strong starting point: it is practical, lightweight, and oriented to a real use-case. It is not yet a full personal AI operating system, but it has the right instincts.

The safest path is not a dramatic rewrite. It is to preserve the working automation, add a real task and academic data model, and then layer the Priority Engine, career intelligence, and dashboard experience on top of that foundation.

This approach keeps the project valuable while progressing toward the full Campus Copilot vision without breaking the current system.
