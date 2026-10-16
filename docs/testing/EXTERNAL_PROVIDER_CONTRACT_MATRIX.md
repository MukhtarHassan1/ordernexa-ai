# External provider verification matrix

OrderNexa separates **implemented**, **contract-verified offline**, **configured**, **remote acknowledged**, and **live verified** states. Offline mocks validate our request/response contracts and safety boundaries; they do **not** prove tenant permissions, provider credentials, quotas, network reachability, or visible remote delivery.

| Provider / boundary | What the source verifies without a paid account | Live acceptance still required before a production claim |
|---|---|---|
| Microsoft Graph mail | App-only token boundary, mail message/attachment parsing, subscription payload, public HTTPS callback constraints, clientState bounds, lifecycle/delta recovery contracts | Entra tenant, `Mail.Read` application permission/admin consent, real mailbox, public callbacks, subscription creation and notification receipt |
| SharePoint via Graph | File upload contract, path safety, byte-for-byte readback contract | Real drive/site permission (`Sites.Selected` or chosen least-privilege grant), remote upload + hash/byte verification |
| Outlook via Graph | Unsent draft create/readback contract and explicit-send boundary | Real mailbox draft visibility; explicit send only if owner enables customer email and approves the test recipient |
| Teams | HTTPS Workflows URL allowlist and separation of HTTP acknowledgement from visible delivery | Real Teams Workflow endpoint and a human-observed channel message |
| HubSpot | Company/contact upsert/readback adapter contracts and deterministic external-reference handling | Real private-app/sandbox token, scopes, upsert + read-after-write |
| Vapi | API Request tool paths/methods match FastAPI OpenAPI; voice status is privacy-minimized; change request is review-only | Public HTTPS OrderNexa endpoint, Vapi credential/tool setup, real test call |
| Twilio | Architectural boundary: Twilio credentials never enter FastAPI; Twilio terminates telephony and hands the call to Vapi | Real Twilio number/account or Vapi-imported number and end-to-end phone call |
| Stripe | Test-mode-only key gate, Checkout Session payload/idempotency, amount/currency verification, webhook signature/replay checks | Real Stripe **test-mode** account, Checkout completion, signed webhook receipt |
| OIDC | JWT issuer/audience/algorithm/JWKS/RBAC controls are testable locally with synthetic keys | Real identity provider and role-by-role login acceptance |

## Run the offline provider contract suite

From the repository root:

```bash
bash scripts/provider-contract-verify.sh
```

The suite intentionally performs **no live provider writes**. A passing result means the adapter contract and safety boundary are internally consistent with the source under test, not that a third-party account has been provisioned.

## Release-claim rule

A provider may be described as **implemented / contract-tested** after the offline suite passes. Use **live verified** only after the actual remote object/event is observed and, where material, read back through the provider API. This is the same evidence-first rule used by the Release Readiness screen.
