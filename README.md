# SmartPPS-Hackathon

This project is a hackathon prototype that previously used Firestore. It has been updated to use Supabase for persistence and realtime updates.

**Supabase Details (configured in the app)**
- URL: `https://rdqbxfujtmpoeyqfwwll.supabase.co`
- Publishable Key: `sb_publishable_JeBUvr0YNVsQOi6ZeAvViA_JW5134nF`

Files added/changed:
- `index.html` — replaced Firebase/Firestore logic with Supabase client initialization and CRUD functions (`saveFamilyData`, `loadFamilyData`).
- `supabase.sql` — SQL to create the `profiles` table, RLS policies, realtime publication, and an `updated_at` trigger.

Setup notes
 - In Supabase SQL editor (or via psql), run `supabase.sql` to create the `profiles` table and policies.
 - Ensure Row Level Security (RLS) is enabled (the SQL already enables it and creates policies that require authenticated users matching `id`).
 - To allow client-side inserts/updates, users must authenticate with Supabase Auth and the `id` must be the user's `auth.users.id`.

Auth from browser (magic link)
 - The app now includes a simple email-based magic-link sign-in UI in the header. Enter an email and click "Sign in (magic link)". Approve the link from the email to create a Supabase session.
 - After sign-in, the client will use the authenticated `user.id` as the `profiles.id` so RLS policies will allow read/write for that row.
 - Make sure Email sign-in is enabled in your Supabase project Auth settings.

How to enable Email (magic link) sign-in in Supabase

1. Open your Supabase project dashboard: `https://app.supabase.com` -> select your project.
2. In the left sidebar, go to **Authentication** -> **Settings** (or **Auth > Settings**).
3. Under **Sign-in methods** / **Enable sign-ups**, ensure **Email** sign-in is enabled. Supabase supports email magic links by default for email-based auth.
4. Configure an SMTP provider so Supabase can send emails (required for production): go to **Authentication** -> **Settings** -> **Email** (or **SMTP**) and enter your SMTP server details (host, port, username, password, sender address). For development you may use a testing SMTP service.
5. Optionally configure email templates and expiration times in the same settings area.

Notes:
- Magic links require email delivery — if emails are not delivered, check your SMTP settings and verify the sending domain.
- For quick testing without SMTP you can use Supabase's built-in email service (may have limits) or inspect the debug logs in Supabase dashboard.
- Keep your SMTP credentials secure and do not commit them to public repositories.

JamAI Base / LLM integration
 - A lightweight `config.js` file is included and can be used to provide `window.JAMAI_PAT` and `window.JAMAI_PROJECT_ID` for the client.
 - WARNING: Storing PATs in client-side files is insecure. For development it's acceptable, but in production you should proxy requests through a server or use secure environment injection.

Local testing
 - Serve the folder and open `index.html` in the browser (simple static server suggested).
 - The app will initialize Supabase using the publishable key; to perform reads/writes protected by RLS you must sign in with the magic-link flow added to the header.

If you want, I can:
 - Add additional auth UX (social providers, password sign-in) or a server-side proxy to safely hold JamAI PATs.
 - Wire JamAI Base calls to use a server-side secret (recommended) or demonstrate a secure dev-only flow.
