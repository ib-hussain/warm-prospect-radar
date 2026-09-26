# Security boundaries

- The crawler accepts HTTP(S) URLs only and rejects hosts resolving to loopback, private, link-local, reserved, or multicast addresses.
- Every redirect target is resolved and checked again before it is requested.
- `robots.txt` is respected by default.
- Public social fallback does not use saved browser cookies, login automation, CAPTCHA solving, or access-control circumvention.
- Raw HTML-derived data is treated as untrusted input. Templates escape extracted content by default.
- Secrets are read from `.env` and are never rendered by the settings page.
- Supabase table/RPC privileges are revoked from `anon` and `authenticated`; the server requires a secret/service-role key and rejects recognisable publishable keys.
- Snapshot download paths are resolved and required to remain inside the configured storage root.
- The default server binds to `127.0.0.1`.
- Outreach delivery requires an approved draft and a separate central feature switch.
- Delivery defaults to `dry_run`; live email requires SMTP and other channels require an authorised webhook.
- Webhook payloads can be HMAC-signed with `OUTREACH_WEBHOOK_SECRET`.
- Simulated delivery is labelled and does not count as a real scoring attempt.

This application intentionally has no users, login, tenant ownership or Row Level Security. Anyone who can reach the Flask service can read central records, alter feature switches, approve drafts and initiate configured delivery. Run it only on a trusted machine or private network. Before internet-facing deployment, place it behind an authenticated reverse proxy or private access gateway and add CSRF protection, HTTPS, request quotas, outbound allow-lists and secret rotation. Docker uses Gunicorn, but the network boundary remains the operator's responsibility.

Report a suspected vulnerability privately to the project owner. Do not include credentials or personal data in an issue report.
