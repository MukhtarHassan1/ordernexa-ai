# External integration boundaries — implementation versus activation

The release contains contract-tested Microsoft Graph and HubSpot *transport adapters*,
not an activated Microsoft/HubSpot account. There are intentionally no hidden,
synthetic "successful" SharePoint/Outlook/CRM writes.

- `app/integrations/microsoft_graph.py` includes explicit read-mail/attachment,
  authorized drive-file upload and separately approved mail-send primitives.
  Live use needs an Entra app/token source, suitable application/delegated
  permissions, admin consent, and Sites.Selected assignment when configured.
- `app/integrations/hubspot.py` supports idempotent email-property contact
  upsert. Live use needs a private app token and permissions.
- `Odoo` is the deep local ERP integration; the pre-existing connector was
  confirmed healthy by user logs, but a new approved order and replay must still
  be exercised on the user's actual Docker instance.
- `MinIO` currently acts as the working local archive for the downstream
  demonstration. **Completing the local archive does not imply actual SharePoint,
  Outlook, Teams, or CRM synchronization.** Those connectors must be wired to
  durable integration commands, credentialed, and end-to-end verified.
- Teams channel messages require a compatible delegated Graph permission and
  organization policy; application-only Mail.Read alone does not authorize
  Teams messaging. Do not assume a Microsoft token supports every action.

Production readiness requires OAuth/OIDC, scoped identities, signed webhook
verification, bounded retries, circuit breakers, dead-letter queues, token
rotation, and provider-specific contract/integration tests.
