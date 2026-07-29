# Disclosure Change Intelligence — Web

Next.js (App Router) + React + TypeScript frontend for the JSE disclosure-
intelligence application. Reads only from the read-only `app.current_*`
views of the Milestone 7A.1 application database via the `app_readonly`
role — never the research database, never publisher credentials.

See [`../docs/frontend.md`](../docs/frontend.md) for full setup,
architecture, environment variables, testing, deployment, and quality-label
documentation.

## Quick start

```bash
pnpm install
cp .env.example .env.local   # set APP_READONLY_DATABASE_URL
pnpm dev
```

## Commands

| Command | Purpose |
|---|---|
| `pnpm dev` | Local development server |
| `pnpm build` | Production build |
| `pnpm start` | Run the production build locally |
| `pnpm test` | Unit, repository, and component tests (Vitest) |
| `pnpm test:seed` | Seed the frontend test application database |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm lint` | ESLint |
