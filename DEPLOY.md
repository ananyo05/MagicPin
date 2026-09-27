# Deploying Vera Message Engine

I can't push code or call hosting APIs from this sandbox (no outbound network
here), so this is a walkthrough for you to run. Everything the platforms need
is already in this folder: `Procfile`, `render.yaml`, `Dockerfile`,
`.dockerignore`, `.gitignore`.

**Before you start:** don't commit `.venv/` — it's a 50MB macOS-specific
virtualenv with compiled binaries that won't run on Linux hosts anyway. The
`.gitignore` added here excludes it. Only `requirements.txt` is needed; every
platform below installs fresh dependencies from it.

---

## Option A — Render (recommended: simplest, free tier, has a health check)

1. Push this folder to a new GitHub repo (`.venv` will be skipped thanks to
   `.gitignore`):
   ```bash
   cd Magicpin
   git init
   git add .
   git commit -m "Vera Message Engine submission"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
2. Go to https://dashboard.render.com → **New** → **Blueprint**.
3. Connect the repo. Render will detect `render.yaml` automatically and
   pre-fill the service (build command, start command, Python version,
   health check path `/v1/healthz`) — just click **Apply**.
4. Wait for the build/deploy to finish (a couple of minutes). Render gives
   you a URL like `https://vera-message-engine.onrender.com`.
5. Sanity check:
   ```bash
   curl https://vera-message-engine.onrender.com/v1/healthz
   ```
   Should return a 200 with a status payload.

Note: Render's free tier spins down on idle and takes ~30-50s to wake up on
the next request — the first `full_evaluation` call after a period of
inactivity may time out or feel slow. If that's a problem for judging, use a
paid instance or Option B/C below.

## Option B — Railway

1. Push to GitHub as in step 1 above (or use `railway up` from the CLI
   without GitHub).
2. https://railway.app → **New Project** → **Deploy from GitHub repo**.
3. Railway auto-detects the `Procfile` (`web: uvicorn app:app --host 0.0.0.0
   --port $PORT`) — no extra config needed.
4. Once deployed, click the service → **Settings** → **Networking** →
   **Generate Domain** to get a public URL.

## Option C — Fly.io (uses the included Dockerfile)

1. Install `flyctl` and log in: `fly auth login`
2. From inside `Magicpin/`:
   ```bash
   fly launch --no-deploy   # detects the Dockerfile, asks for an app name/region
   fly deploy
   ```
3. `fly status` shows your public URL (`https://<app-name>.fly.dev`).

---

## After deployment (steps 2 and 4 from the handoff)

Regenerating `submission.jsonl` doesn't require the deployed URL (it calls
`engine.compose.compose` directly against the canonical test pairs) — that's
already done as of this session; see `submission.jsonl`.

To re-run the real LLM-judge evaluation against your **public** URL instead
of localhost:

```bash
cd Magicpin
export BOT_URL="https://<your-deployed-url>"
export LLM_PROVIDER=groq
export LLM_API_KEY="<your groq key>"
export LLM_MODEL="openai/gpt-oss-120b"   # judge_simulator's own default model string is deprecated — always set this explicitly
export TEST_SCENARIO=full_evaluation
python judge_simulator.py
```

Reminders from the handoff notes, still accurate:
- The Groq key in use is a **free-tier key you planned to delete** — swap in
  a fresh one if that's already happened.
- `full_evaluation` batches 100 triggers with ~3s pacing between Groq calls
  plus occasional 429 backoff — budget several minutes for the full run.
- Compare the resulting score against the last local run (76%) as a sanity
  check that the deployed instance behaves identically to local.
