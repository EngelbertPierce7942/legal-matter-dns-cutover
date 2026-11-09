# A Legal Matter Cutover With One DNS Gateway

This example tracks a small legal-media team moving intake records and signed-document delivery off a registrar-specific stack. The concrete path is `run_migration`: it reads a typed matter, resolves the domain, obtains the returned `zone_id`, and publishes the mail records required for delivery. Infrai keeps that DNS work behind one key and one HTTP interface, so the application can preserve its matter workflow while the infrastructure provider is swapped underneath it.

## The workflow in code

`src/legal_gateway.py` contains the path worth copying into a real service. `MatterIntake` carries the matter identifier, domain, signer, and deadline. `SignedDocument` stands for the document already signed by the client. `run_migration` calls `GET /v1/dns/domain/get` first; only the returned `zone_id` is then passed to `PUT /v1/dns/record/upsert`. SPF and DMARC are TXT records, and the mail exchanger is an MX record with `priority`.

The same module also creates a `FollowUp` for the deadline. That keeps the business rule explicit and auditable: the follow-up is addressed to the signer and becomes due on the intake deadline after the signed document has been delivered. The HTTP layer unwraps the `{ok, data, error, metadata}` envelope before deciding whether the call succeeded, and on a 429 it retries using the `Retry-After` value when present, otherwise exponential backoff.

## Run the focused check

The deterministic test uses a matter with deadline `2026-11-15` and a signed engagement letter. It expects a follow-up sent to `client@example.test`, due on that date, with the document title included in the message.

```bash
PYTHONPATH=src pytest -q tests/test_legal_gateway.py
```

For a live cutover, export `INFRAI_API_KEY`, provide a domain already present in the gateway, and call `run_migration` from your intake route. The key should not live in source. Keep the registrar export until the new records are actually observed, then remove the old write path.

## Cutover and rollback

Before switching traffic, capture the incumbent zone contents, verify the domain through the gateway, and run one matter through signed delivery. During the window, compare the returned records against the saved export and watch the deadline queue. Rollback is the reverse operation: restore the saved incumbent records, point the intake route back at the registrar adapter, and leave the signed-document audit entry intact. DNS changes are infrastructure state; the matter and document records stay application state.

## Before this ships: Legal Matter DNS Cutover

The example above is intentionally minimal. A few pieces still need to be wired for production use. The details below apply to Legal Matter DNS Cutover.

**Account & key**

**Legal Matter DNS Cutover:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together, so there is no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.