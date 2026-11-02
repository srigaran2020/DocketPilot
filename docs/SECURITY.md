# DocketPilot security

What protects DocketPilot, why each control exists, and what is still open. The controls are mapped to the
OWASP Top 10:2025, the OWASP Top 10 for LLM Applications (2026) and ASVS 5.0. Tests: `tests/test_security.py`,
`tests/test_hardening.py`, `tests/test_privacy.py`, `tests/test_auth_signup.py`.

DocketPilot is a research prototype that runs on one laptop (`127.0.0.1`). It has not had an external
penetration test, so no one can promise "no vulnerabilities". What this document claims is narrower: the
checks below were reviewed against the OWASP lists, and each one has an automated test.

## 1. Accounts and sign-in

| Control | Purpose | Where |
|---|---|---|
| Passwords stored as **Argon2** hashes | A stolen database does not reveal passwords; Argon2 is slow on purpose, so guessing is expensive | `security.py` |
| **Password rules**: at least 8 characters; common passwords (`password123`, `india@123` …) refused; the user's name or email inside the password refused | Stops the passwords attackers try first (ASVS 6.2.1, 6.2.4) | `security.password_problem` |
| **Brute-force lock**: 10 failed attempts per minute per address, and 10 per 15 minutes per account | Slows password guessing, including guessing one account from many addresses (ASVS 6.3.1) | `api/auth.py` |
| **Google sign-in (OAuth 2.0 / OpenID Connect)**: Google's signed ID token is checked with Google; it must be issued by Google, for *this* app's client ID, with a verified email | Sign-in without a password; a token made for another website is refused | `api/auth.py` `/auth/google` |
| **Signed access tokens (JWT, HS256)** with expiry; `exp`, `iat`, `sub` required | A token cannot be forged or edited without the server's secret | `security.py` |
| **Sign-out cancels tokens** (`token_version`): signing out or changing the password makes every earlier token useless, on every device | A stolen or copied token stops working once you sign out (ASVS 7.4.1) | `api/deps.py`, `api/auth.py`, migration 0006 |
| **Server refuses to start with a weak secret** (shorter than 32 characters or a default) | Prevents anyone forging sign-in tokens | `api/main.py` |
| Errors never say which part was wrong ("Wrong email or password") | Does not reveal which emails have accounts | `api/auth.py` |

## 2. Who can see what (access control)

| Control | Purpose |
|---|---|
| Every case, paper, draft, reminder and calendar query is filtered by the user's **workspace (firm)** on the server | One user can never open another user's case by changing an ID in the address (IDOR, OWASP A01) |
| A malformed ID returns **404 Not found** | No database details are leaked in error messages (A10) |
| **Roles**: only an advocate or admin can approve a draft; only an admin can add users | Juniors cannot sign off work |
| **Append-only audit log**: a database trigger refuses to edit or delete audit rows. Sign-in, failed sign-in, sign-out, password change, uploads and approvals are all logged | A record of who did what that cannot be quietly changed (A09) |

## 3. Client privacy

| Control | Purpose |
|---|---|
| **Masking before the AI**: names, phone numbers, Aadhaar, PAN, addresses and so on become `PERSON_1`-style labels before any text goes to the AI | Client identities never leave the laptop (LLM02 Sensitive Information Disclosure) |
| **Encrypted vault** (Fernet, key in `.env`) holds the label → real-name table for each case; vault file names are checked against path tricks | Real names are put back only on the lawyer's own screen and in the approved Word file |
| Secrets (`JWT_SECRET`, `VAULT_KEY`, Groq keys, database password) are kept only in `.env`, which git ignores | Secrets are never committed to GitHub |

## 4. The browser (web hardening)

All responses get these headers (`api/hardening.py`):

| Header | Purpose |
|---|---|
| `Content-Security-Policy`: scripts only from this server and Google's sign-in script (the one inline theme script is allowed by its SHA-256 hash, not by `unsafe-inline`); no plugins; `frame-ancestors 'none'` | Even if someone slipped script into a page, the browser would refuse to run it (XSS); other sites cannot frame DocketPilot (clickjacking) |
| `X-Frame-Options: DENY` | Clickjacking protection for older browsers |
| `X-Content-Type-Options: nosniff` | An uploaded file cannot be treated as a script |
| `Referrer-Policy: strict-origin-when-cross-origin` | Page addresses (which may contain case IDs) are not sent to other sites |
| `Permissions-Policy`: camera, microphone, location, payment, USB off | The page cannot ask for devices it never needs |
| `Cache-Control: no-store` on API answers | Case data is not stored in the browser cache |
| `Cross-Origin-Opener-Policy: same-origin-allow-popups` | Isolates the window while still allowing Google's sign-in pop-up |

React escapes all text by default, and the app does not use `dangerouslySetInnerHTML` anywhere. The interactive
API documentation (`/docs`) is switched off unless `API_DOCS=true` is set for development.

## 5. Uploads and input

| Control | Purpose |
|---|---|
| A request larger than 16 MB is refused **before it is read** (also for requests without a declared size); uploads are capped at 15 MB | One huge upload cannot exhaust the laptop's memory |
| The file's **content must match its extension** (a PDF must start with `%PDF-`, a .docx must be a real zip, a .txt must not be binary); other types are refused | Renamed or disguised files are rejected |
| PDF limited to 500 pages; a .docx that expands beyond 100 MB is refused ("zip bomb") | Small files that explode when opened are refused |
| Damaged or password-protected files give a clear message (422), not a server error | No stack traces; the user knows what to fix |
| Every input field has a length limit; all database queries are parameterised | Prevents SQL injection (A05) and oversized input |

## 6. The AI (LLM-specific risks)

| Control | Purpose |
|---|---|
| **AI usage limit**: at most 30 AI requests per user in 10 minutes | One account cannot use up the shared Groq quota (LLM10 Unbounded Consumption) |
| Every Groq request stays under 8,000 tokens | Keeps within Groq's limits |
| The AI **cannot act**: requests are routed by fixed rules, the AI has no tools, and it cannot send, file or delete anything; a draft needs the lawyer's approval | A prompt hidden in an uploaded paper cannot make the system do anything (LLM01 Prompt Injection, LLM06 Excessive Agency) |
| **Every citation in AI output is checked** against the stored judgment or Act; wrong ones are corrected or removed; the AI's text is shown as text, never run as code | Made-up law does not reach the lawyer unflagged (LLM05/LLM09) |
| Legal text comes only from India Code and the judgment corpus, never from the model | The source of truth stays outside the AI |

## 7. Known limits (honest list)

- **HTTPS**: the app runs on `127.0.0.1` and never leaves the laptop, so it uses plain HTTP. Before any deployment
  on a network: put it behind HTTPS and add `Strict-Transport-Security`.
- **Token storage**: the sign-in token is kept in the browser's local storage. The strict Content-Security-Policy
  is what protects it. An httpOnly cookie with CSRF protection would be stronger.
- **Counters reset on restart**: the brute-force and AI-usage counters are kept in memory, so restarting the
  server clears them. A shared store (Redis) would be needed for several servers.
- **No two-factor sign-in** for password accounts. Google accounts can use Google's own 2-step verification.
- **`/classic`**: the old one-file page has a looser policy (inline scripts) because it was written that way.
- **No external penetration test** has been done.

## 8. Setting up Google sign-in

1. Go to <https://console.cloud.google.com/> → create a project (for example "DocketPilot").
2. **APIs & Services → OAuth consent screen**: choose *External*, fill in the app name and your email, and add
   your own Google account as a *test user*.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → *Web application*.
   Under **Authorised JavaScript origins**, add `http://127.0.0.1:8000` and `http://localhost:8000`.
   No redirect URI is needed.
4. Copy the **Client ID** (it ends in `.apps.googleusercontent.com`) into `.env`:
   `GOOGLE_CLIENT_ID=1234-abc.apps.googleusercontent.com`
5. Restart the app (`.\start.ps1`). The "Sign in with Google" button appears on the sign-in page.

The client ID is not a secret. No client secret is used, because the app only verifies Google's signed ID token.
