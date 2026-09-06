# ReviewPulse

**Customer Review Triage & Aggregation Agent** — built with the [Strands Agents SDK](https://strandsagents.com) for the AWS "Agents for Humans" hackathon (Professional Agents track).

> Status: early build. This README will grow as the project does — see `docs/` for the architecture diagram once added.

## What it does

ReviewPulse continuously pulls customer reviews from the App Store, classifies each one by sentiment and problem type, and **aggregates many reviews into a small number of engineering tickets** in Jira — instead of one ticket per review. It stays silent unless it detects signs of a genuine reputation crisis (a sudden burst of negative reviews), at which point it escalates to a human with a drafted holding statement.

The headline metric is suppression: thousands of raw reviews should collapse into a handful of tickets and, ideally, zero-to-one human escalations. Silence is the feature.

**Who it's for:** a product/support lead at a small app company who currently reads app reviews by hand and manually files bugs from them.

## How it works

1. **Ingest** — pulls new reviews from the Apple App Store customer-review RSS feed.
2. **Triage** — an LLM classifies each review (sentiment, bug/feature/praise category, severity, feature area).
3. **Cluster** — groups triaged reviews describing the same underlying issue.
4. **Ticket sync** — once a cluster crosses a threshold, creates or updates a Jira issue.
5. **Crisis detection** — pure statistical burst-detection on review volume/sentiment; only when it trips does an agent draft an escalation for a human.

See the plan/architecture notes for full details (added as the project progresses).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env        # fill in Jira credentials
```

Requires AWS credentials with Bedrock access (Claude Haiku/Sonnet) configured via `aws configure` or environment variables.

## Running locally

```bash
python -m reviewpulse.cli --once          # single ingest/triage/ticket pass
python -m reviewpulse.cli --replay <path> # replay a fixture corpus (no network calls)
```

## License

MIT — see [LICENSE](LICENSE).
