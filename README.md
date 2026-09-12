# ReviewPulse

**Customer Review Triage & Aggregation Agent** — built with the [Strands Agents SDK](https://strandsagents.com) for the AWS "Agents for Humans" hackathon (Professional Agents track).

> Status: early build. This README will grow as the project does — see `docs/` for the architecture diagram once added.

## What it does

ReviewPulse loads customer reviews (currently from a frozen Spotify Google Play export), classifies each one by sentiment and problem type, and **aggregates many reviews into a small number of engineering tickets** in Jira — instead of one ticket per review. It stays silent unless it detects signs of a genuine reputation crisis (a sudden burst of negative reviews), at which point it escalates to a human with a drafted holding statement.

The headline metric is suppression: thousands of raw reviews should collapse into a handful of tickets and, ideally, zero-to-one human escalations. Silence is the feature.

**Who it's for:** a product/support lead at a small app company who currently reads app reviews by hand and manually files bugs from them.

## How it works

1. **Ingest** — loads new reviews from a Spotify review CSV export (`reviewpulse/sources/spotify_csv.py`).
2. **Triage** — an LLM classifies each review (sentiment, bug/feature/praise category, severity, feature area).
3. **Cluster** — groups triaged reviews describing the same underlying issue.
4. **Ticket sync** — once a cluster crosses a threshold, creates or updates a Jira issue.
5. **Crisis detection** — pure statistical burst-detection on review volume/sentiment; only when it trips does an agent draft an escalation for a human.

See the plan/architecture notes for full details (added as the project progresses).

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .            # installs reviewpulse + dependencies from pyproject.toml
cp .env.example .env        # fill in Jira credentials once the ticket-sync stage is added
```

Requires AWS credentials with Bedrock access (Claude Haiku 4.5 / Sonnet) for the triage/cluster/crisis
stages. Locally, use `aws login` (browser-based, short-lived session credentials — no static keys to
manage) rather than a long-lived access key:

```bash
aws login                    # opens a browser; session expires, rerun when it does
aws sts get-caller-identity  # confirm it took
```

> **Gotcha:** the `aws login` credential provider is only readable by boto3 when botocore's CRT extra
> is installed. Without it every Bedrock call fails with `MissingDependencyException` even though the
> AWS CLI itself works fine. `botocore[crt]` is pinned in `pyproject.toml` for this reason — if you
> install dependencies some other way, install that extra too.

## Running locally

```bash
python -m reviewpulse.cli --replay tests/fixtures/review_corpus.json  # replay a frozen fixture corpus (no network calls)
```

Dedupes against a local SQLite store (`data/reviewpulse.db` by default, override with `--db`) so
re-running is idempotent — already-seen reviews are silently skipped.

For a live-feeling run against the full Spotify CSV, use `scripts/demo_loop.py` instead — it releases
the file in bounded chunks on an interval (simulating a scheduled poll of a live source) rather than
loading it all at once:

```bash
python scripts/demo_loop.py                                # 15-min interval, 50 reviews/chunk
python scripts/demo_loop.py --interval 5 --chunk-size 20    # fast pacing for a live demo
python scripts/demo_loop.py --once                          # single tick, no loop
```

### Refreshing the fixture corpus

```bash
python scripts/capture_fixtures.py
```

Freezes a reproducible 2,000-review sample from `reviewpulse/sources/spotify_reviews.csv` into
`tests/fixtures/review_corpus.json`. This is what `--replay` and the demo video run against, so the
project works against a small, stable corpus rather than the full ~84k-row CSV.

### Evaluating the triage stage

```bash
python scripts/eval_triage.py --limit 100 --dry-run   # prompt preview, no API calls, no cost
python scripts/eval_triage.py --limit 100             # real Bedrock calls
```

Classifies a reproducible random sample of the fixture corpus and prints the category / sentiment /
severity distribution, plus any rating-versus-label mismatches worth eyeballing (a 1-star review
labelled "praise", say). Results are cached in the store keyed by review id, so re-running only pays
for reviews it hasn't already classified.

## Cost control

Two-tier model routing: **Haiku 4.5** handles bulk triage, which is the only stage every review
passes through and therefore the only one whose cost scales with volume. The more expensive model is
reserved for cluster adjudication and crisis drafting — low volume, high consequence. Reviews are
classified once ever and cached in SQLite, batched 20 to a call, so the full 2000-review corpus costs
well under a dollar and a re-run costs nothing.

## Testing

```bash
pytest
```

Every test runs offline against saved fixtures — no network, no AWS credentials, no cost. The triage
tests use a stub agent and cover the failure modes that would corrupt data (a verdict landing on the
wrong review, a duplicate or out-of-range index, a batch that throws).

## License

MIT — see [LICENSE](LICENSE).
