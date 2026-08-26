# Incident Report — INC-2291

## Summary

On 14 March a configuration change to the search tier made document ingestion
fail for **4 hours and 12 minutes**. No customer data was lost. 1,847 uploads
were queued and replayed once service was restored.

Severity was set to **SEV-2**. The incident commander was the platform on-call
engineer.

## Timeline

**09:14** — A change to the indexing worker was merged and deployed to
production. The change reduced the connection pool from 32 to 4 to lower memory
use.

**09:31** — Ingestion latency alerts fired. The first alert was dismissed as
noise because a large customer had begun a bulk import that morning.

**10:05** — Upload success rate dropped below 40%. The alert escalated and an
incident was declared under ticket **INC-2291**.

**10:22** — The team suspected the bulk import and applied a rate limit to that
customer. This had no effect, costing roughly 25 minutes.

**11:40** — A engineer correlated the start of failures with the deployment
timestamp and identified the connection pool change.

**12:18** — The change was reverted. Ingestion recovered within four minutes.

**13:26** — The queued backlog finished replaying and the incident was closed.

## Root Cause

The connection pool was reduced from 32 to 4 without accounting for the worker's
concurrency setting, which remained at 16. Sixteen concurrent tasks competed for
four connections, so most timed out after the 30-second limit.

The change passed review because the reviewer checked memory impact but not the
relationship between pool size and worker concurrency. No test covered that
interaction.

Staging did not reproduce the failure because staging runs a single worker with
concurrency 2, which four connections comfortably serve.

## Contributing Factors

The first latency alert was dismissed without checking recent deployments. The
runbook did not list "check recent deploys" as the first diagnostic step.

Deployment timestamps were not visible on the ingestion dashboard, so correlating
the failure with the deploy required manually opening a separate tool.

## Action Items

**AI-1** — Add an assertion that pool size is at least equal to worker
concurrency, failing startup otherwise. Owner: platform team. Due 28 March.

**AI-2** — Overlay deployment markers on the ingestion dashboard. Owner:
observability team. Due 4 April.

**AI-3** — Make staging concurrency match production. Owner: platform team.
Due 11 April.

**AI-4** — Add "check recent deploys" as step one of the ingestion runbook.
Owner: on-call rotation lead. Due 21 March.

## Lessons

Resource limits are relationships, not independent numbers. A pool size is only
meaningful next to the concurrency that draws from it.

An environment that differs from production in the dimension being changed
cannot validate that change.
