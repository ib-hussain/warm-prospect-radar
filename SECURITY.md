# Security boundaries

- The crawler accepts HTTP(S) URLs only and rejects hosts resolving to loopback, private, link-local, reserved, or multicast addresses.
- Every redirect target is resolved and checked again before it is requested.
- `robots.txt` is respected by default.
- Public social fallback does not use saved browser cookies, login automation, CAPTCHA solving, or access-control circumvention.
- Raw HTML-derived data is treated as untrusted input. Templates escape extracted content by default.
- Secrets are read from `.env` and are never rendered by the settings page.
- Snapshot download paths are resolved and required to remain inside the configured storage root.
- The default server binds to `127.0.0.1`.

The requested first-version Supabase schema disables Row Level Security. Run the application only on a trusted machine or private network. Before internet-facing deployment, add authenticated users, per-tenant authorization, RLS policies, CSRF protection, production WSGI hosting, HTTPS, request quotas, and secret rotation.

Report a suspected vulnerability privately to the project owner. Do not include credentials or personal data in an issue report.

