# FreelanceHub — Mobile

Expo (SDK 57) + Expo Router + strict TypeScript, connected to the FastAPI backend in `../backend`.

## Run

1. Start the backend (from the repo root): `docker compose up -d` (API on port 8000).
2. Start the app:

```bash
npm install
npx expo start          # press a (Android) / i (iOS) / w (web)
```

### Which server does the app call?

| Situation | API URL |
|-----------|---------|
| `EXPO_PUBLIC_API_URL` is set | that URL (`/api/v1` is appended if missing) |
| Phone with Expo Go on the same Wi-Fi | `http://<your PC's LAN IP>:8000/api/v1` — taken automatically from the Metro host |
| Web (`w`) | `http://localhost:8000/api/v1` (set `CORS_ORIGINS=["http://localhost:8081"]` for the API) |
| Android emulator | `http://10.0.2.2:8000/api/v1` |

With `npx expo start --tunnel` the Metro host is a tunnel, so set `EXPO_PUBLIC_API_URL` to an address the phone can
reach. On Windows, allow inbound TCP 8000 in the firewall for the phone to reach Docker. The URL in use is shown on
the sign-in screen and in Settings → Connection.

## Quality checks

```bash
npm run typecheck       # tsc --noEmit (strict, noUncheckedIndexedAccess)
npm run lint            # eslint-config-expo (incl. React Compiler hook rules)
npm test                # jest-expo + React Native Testing Library
npm run check           # all three
```

## Structure

```
src/
├── app/                        # Expo Router routes (thin screens)
│   ├── _layout.tsx             # providers, splash, session restore, Stack.Protected guards
│   ├── (auth)/sign-in.tsx · sign-up.tsx     # only reachable when signed out
│   ├── (tabs)/                 # Dashboard · Projects · Time · Clients · Settings
│   ├── projects/[id].tsx · new.tsx
│   ├── clients/[id].tsx · new.tsx
│   ├── invoices/index.tsx · new.tsx · [id].tsx · edit/[id].tsx   # list, create, detail/payments/PDF, edit draft
│   ├── analytics.tsx           # breakdown by project/client, CSV export
│   └── settings/components.tsx # living design-system gallery
├── features/<feature>/
│   ├── api.ts                  # TanStack Query hooks + mutations for the feature
│   ├── schema.ts               # Zod form schemas (mirror backend rules; messages are i18n keys)
│   └── components/             # presentational components (data via props)
│   ├── auth/session.ts         # sign-in/up/out, session restore, profile updates
│   └── timer/                  # model.ts (pure state machine), api.ts (commands), clock.ts, persistence.ts
└── shared/
    ├── api/                    # typed fetch client, ApiError, token storage, mappers, query keys
    ├── theme/ · ui/ · lib/ · i18n/
    └── types/domain.ts         # camelCase domain types (wire types live in shared/api/wire.ts)
```

## Data, auth and the timer

- **Tokens**: refresh token only in Expo SecureStore (Keychain / Keystore), access token only in memory. On web there
  is no encrypted storage, so the session is memory-only and ends on reload. Nothing secret is written to AsyncStorage.
- **Session restore**: during the splash screen the stored refresh token is exchanged for a new pair. Offline, the app
  opens from the cached (non-secret) profile and shows an offline banner.
- **Requests**: `shared/api/client.ts` adds the bearer token, refreshes once on 401 (single-flight, shared by parallel
  requests) and turns RFC 9457 errors into `ApiError`; screens show translated messages via `errorMessageKey()`.
- **Timer**: elapsed time = server-clock now − `started_at` − pauses. The last server-confirmed state and the clock
  offset are saved in AsyncStorage and restored on the next launch, so the timer survives backgrounding and restarts.
  Commands carry an `Idempotency-Key`, a client-generated entry id (start) and the tap timestamp; transient failures
  are retried with the same key, so a command is never applied twice.
- **Money**: amounts arrive as decimal strings and are formatted, never summed across currencies. The only client-side
  arithmetic is the new-invoice preview, done in integer cents with the server's half-up rules; the stored invoice
  returned by the API is what is shown afterwards. Mutations (timer, entries, invoices, payments) invalidate the
  dashboard, analytics and project/client summaries.
- **Files**: CSV and PDF bytes are fetched through the authenticated client (the token never goes into a URL), written
  to the cache with `expo-file-system` and handed to the share sheet (`expo-sharing`); on web they download normally.
- Not yet: persisted offline command queue, edit/archive screens, manual time entries UI.

## Localization

English, Українська, Русский. Default = device language (fallback English); override in Settings → Language
(saved on the device). Strings live in `src/shared/i18n/locales/{en,uk,ru}.ts`; keys are type-checked against
`en.ts`, and tests enforce identical keys and `{{placeholders}}` in every locale. Server errors are shown through
`errors.<CODE>` keys, never as raw server text.

## End-to-end check against a real backend

`scripts/e2e/web_e2e.py` drives the web build with Playwright against a running API and verifies every timer
command in PostgreSQL. Start the API with `ACCESS_TOKEN_TTL_SECONDS=20` and `CORS_ORIGINS=["http://localhost:8090"]`,
export the app with `EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo export --platform web`, serve the export on
port 8090, then run `python3 scripts/e2e/web_e2e.py --db "host=localhost user=postgres dbname=<db>"`.

`scripts/e2e/finance_e2e.py` covers the money features the same way (also start the API with
`REGISTER_RATE_LIMIT=1000 LOGIN_RATE_LIMIT=1000`): dashboard figures per currency, an invoice built in the UI with tax,
editing the draft (incl. a version conflict from another device), two-tap send, entry locking, partial/over/final payments, PDF and both CSV downloads, and cross-user isolation.
