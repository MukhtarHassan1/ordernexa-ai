# OrderNexa AI — 2026-10-04 packaging test evidence

This file records the final checks performed on the hardened source tree in the packaging environment.

| Check | Result |
|---|---|
| Python compile (`apps/api/app`, tests, eval tooling) | PASS |
| Full isolated Python suite | **132 passed** |
| Dedicated external-provider contract file | **19 passed** |
| Node console tests | **11 passed** |
| JavaScript syntax checks | PASS |
| n8n workflow JSON | **5 parsed, all inactive, unique node names** |
| Docker Compose YAML / build-target invariants | PASS |
| Offline release preflight | PASS |
| 500-case generated evaluation draft | **500 cases; 500 require human label review; release-claim eligible = false** |
| Obvious live-secret pattern scan | PASS (no `sk_live_`, `whsec_`, GitHub PAT or AWS access-key pattern detected) |
| Private environment files in release tree | Only `.env.example` |

## Important test boundary

Python tests used an import-only `asyncpg` stub in the packaging environment so modules could load without a running PostgreSQL instance. The stub does not answer SQL queries or fabricate database responses. Database/Odoo/n8n operational acceptance remains separate owner-session evidence.

External-provider tests use synthetic HTTP transports and intentionally perform no remote writes. They validate source contracts and fail-closed behavior, not customer credentials or remote delivery.
