# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability in ENS-Retro-Data, **please do not open a public issue**. Instead, report it privately so we can investigate and ship a fix before details become public.

### How to report

**Preferred:** Use GitHub's private security advisory feature at:
https://github.com/metagov/ENS-Retro-Data/security/advisories/new

**Alternative:** Email the maintainer directly at **rashmi@daostar.org** with:
- A clear description of the vulnerability
- Steps to reproduce
- The affected file(s), line numbers, and commit hash if known
- Your assessment of the severity and impact
- Any suggested remediation

We aim to acknowledge reports within **3 business days** and provide an initial assessment within **7 days**. Severity and response time will depend on the specifics.

## What we consider in scope

- SQL injection or query smuggling in `dashboards/api.py` (the 7-layer SELECT validator)
- Authentication bypasses on `/api/*` or `/mcp` endpoints
- Secrets, credentials, or private data exposed in the repository or git history
- Unsafe deserialization, XSS, or CSRF in the Streamlit dashboard or ChatKit widget
- Supply-chain concerns in our direct dependencies (`pyproject.toml`, `dashboards/requirements.txt`, `dashboards/requirements-api.txt`)
- Data-integrity issues that could allow tampering with governance analysis outputs

## What is NOT in scope

- Vulnerabilities in third-party services we integrate with (Snapshot, Tally, Etherscan, OpenAI, Render) — please report those to the respective vendors
- Issues requiring physical access to a maintainer's machine
- Social engineering against maintainers
- Denial-of-service attacks against the public dashboard that don't involve an application-level bug
- Rate-limit exhaustion via legitimate API usage

## Safe harbor

We will not pursue legal action against researchers who:
- Make a good-faith effort to avoid privacy violations, data destruction, and service disruption
- Give us reasonable time to respond to and fix issues before public disclosure (at least 90 days)
- Do not access or modify data beyond what is necessary to demonstrate the issue
- Do not use the vulnerability for purposes other than reporting it

## Credit

With your permission, we'll acknowledge your contribution in the security advisory and in the project's release notes.

## Disclosed vulnerabilities

None to date.

---

Thank you for helping keep ENS-Retro-Data secure for everyone.
