## Runtime Configuration
Execute python scripts inside the virtual environment. Activation command is source env/bin/activate.

Re-use virtual environment if one is already activated.

## Database Notes
- SQLite database at `data/runrepeat_lab_tests.sqlite`
- Schema: shoes table with JSON lab_test_results column
- Use `pd.read_sql_query()` + `json_normalize()` for ML data
- Crawler uses INSERT OR REPLACE for incremental updates 

## Deployment

### Vercel (Public Web)
- **Project**: `shoe-mapping` (ID: `prj_ewdd0nDFt70iykpEy6fCiOD2Bunt`, org: `team_mqQ1HDQYs3Umhwlw0h8vCi59`)
- **Production URL**: `https://shoe-mapping.vercel.app`
- **Preview deploy**: Push to any non-`main` branch; Vercel auto-creates a preview URL
- **Production deploy**: Merge to `main` or `vercel --prod`
- **CLI preview**: `vercel deploy` (no `--prod` flag) from project root
- Only static JSON artifacts are deployed (`data/shoes.catalog.json`, `data/precomputed_recommendations.json`)
- `.vercelignore` excludes personalization stack, ML scripts, and heavy data files

### Render (Personalization API + Postgres)
- **Blueprint**: `render.yaml` at repo root defines the API and Postgres (worker is commented out; jobs run inline via `INLINE_JOB_EXECUTION=true`)
- **Services**: `shoe-mapping-api` (web), `shoe-mapping-db` (Postgres)
- **Deploy branch**: Currently `personalization-mvp`; switch to `main` when promoting to production
- **Migrations**: `DATABASE_URL='<url>' alembic upgrade head`
- **Env vars**: `DATABASE_URL` wired from Postgres, `SESSION_SECRET` auto-generated, see `IMPLEMENTATION_STATUS.md` for full list
- To wire Vercel ↔ Render: set `PERSONALIZATION_BASE_URL=https://<render-host>.onrender.com` in Vercel project env vars
