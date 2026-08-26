# Meridian Payments API — Reference

## Authentication

All requests require a bearer token in the `Authorization` header. Tokens are
issued per environment and never expire automatically, but may be revoked from
the dashboard.

Sandbox tokens are prefixed `sk_test_` and production tokens `sk_live_`. Sending
a sandbox token to the production host returns HTTP **401** with error code
`auth_environment_mismatch`.

Every response carries an `X-Request-Id` header. Include this value when
contacting support; without it a request cannot be traced.

## Rate Limits

The default limit is **1,000 requests per hour** per token. Merchants on the
Scale plan are raised to 10,000 requests per hour on request.

Exceeding the limit returns HTTP **429** with a `Retry-After` header giving the
number of seconds to wait. Retries before that window elapses do not reset the
counter but do count toward it.

Burst traffic is smoothed over a 60-second window. A client sending 200 requests
in one second is throttled even when its hourly budget is untouched.

## Creating a Charge

`POST /v2/charges` creates a charge. Required fields are `amount` in the
smallest currency unit, `currency` as a three-letter ISO code, and `source`.

The `idempotency_key` field is optional but strongly recommended. Replaying a
request with the same key within **24 hours** returns the original response
rather than creating a duplicate charge.

Amounts must be positive integers. Sending a decimal returns HTTP 400 with error
code `amount_not_integer`.

Charges settle in two business days for domestic transactions and five for
cross-border ones.

## Refunds

`POST /v2/refunds` refunds a charge in whole or in part. A charge may be refunded
multiple times up to its original amount.

Refunds are only possible within **180 days** of the original charge. After that
the endpoint returns error code `refund_window_expired`.

Partial refunds do not release the original authorisation hold; the hold expires
on its own schedule.

## Webhooks

Webhook payloads are signed with HMAC-SHA256. The signature is in the
`Meridian-Signature` header and the signing secret is shown once at endpoint
creation.

Failed deliveries are retried with exponential backoff for **72 hours**, after
which the event is dropped and the endpoint is marked unhealthy.

An endpoint returning non-2xx responses for 24 consecutive hours is disabled
automatically and the account owner is emailed.

Verify signatures before parsing the body. Timestamps older than 5 minutes
should be rejected to prevent replay.

## Errors

Errors return a JSON body with `code`, `message` and `doc_url`. The HTTP status
reflects the class of error: 4xx for client problems, 5xx for ours.

Error code `card_declined` includes a `decline_reason` field. The most common
values are `insufficient_funds`, `expired_card` and `do_not_honor`.
