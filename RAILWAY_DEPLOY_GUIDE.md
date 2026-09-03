# Railway Deployment Guide for Adapt.io Lead Generation Backend

This guide walks you step-by-step through deploying this Django + Playwright backend to [Railway](https://railway.app).

---

## What We Have Configured For You

All necessary configuration files have been prepared and tested:

1. **[`railway.json`](file:///d:/POCS/adapt-io-backend/railway.json)**: Instructs Railway to build with Docker, sets the startup command, defines the health check endpoint (`/api/health/`), and configures automatic restart on failure.
2. **[`Dockerfile`](file:///d:/POCS/adapt-io-backend/Dockerfile)**:
   - Uses `python:3.10-slim`.
   - Installs Linux system dependencies required by Chromium and PostgreSQL.
   - Installs Playwright Chromium browser binaries (`playwright install --with-deps chromium`).
   - Runs `python manage.py collectstatic` to bundle Swagger UI and Admin static assets.
   - Executes `/app/start.sh` on container start.
3. **[`start.sh`](file:///d:/POCS/adapt-io-backend/start.sh)**: Automates database migrations (`python manage.py migrate --noinput`) and starts Gunicorn bound dynamically to Railway's `$PORT`.
4. **[`scraper/browser.py`](file:///d:/POCS/adapt-io-backend/scraper/browser.py)**: Added container-hardening flags (`--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`) so Chromium never crashes in containerized Linux environments.
5. **[`config/settings.py`](file:///d:/POCS/adapt-io-backend/config/settings.py)**:
   - Auto-detects `RAILWAY_PUBLIC_DOMAIN`.
   - Configures `CSRF_TRUSTED_ORIGINS` for `*.railway.app` and `*.up.railway.app`.
   - Configures `SECURE_PROXY_SSL_HEADER` for Railway's HTTPS reverse proxy.
   - Provides safe fallback for database at build-time so `collectstatic` succeeds cleanly.
6. **[`config/urls.py`](file:///d:/POCS/adapt-io-backend/config/urls.py)**: Root path `/` automatically redirects visitors to the interactive Swagger UI (`/api/docs/`).

---

## Prerequisites

1. A [Railway.app](https://railway.app) account.
2. A [GitHub](https://github.com) account (or Railway CLI).
3. Your database connection string (e.g., from [Supabase](https://supabase.com) or a Railway PostgreSQL service).
4. Your API keys (Supabase, MailTester Ninja, Webshare proxy if used).

---

## Step 1: Commit and Push Your Code to GitHub

Open your terminal or PowerShell in your project directory:

```bash
git add .
git commit -m "Configure production Docker and Railway deployment files"
git push origin main
```

*(If you haven't initialized git or pushed yet):*
```bash
git init
git add .
git commit -m "Initial commit with Railway deployment configuration"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo-name>.git
git push -u origin main
```

---

## Step 2: Create a New Project on Railway

1. Go to [railway.app/dashboard](https://railway.app/dashboard).
2. Click the **+ New Project** button (top right).
3. Select **Deploy from GitHub repo**.
4. Choose your repository from the list.
5. Click **Deploy Now**.

Railway will immediately detect your `Dockerfile` and `railway.json` and start the Docker build.

---

## Step 3: Add Environment Variables in Railway

Before or while the build is progressing, set your environment variables:

1. Click on your newly created service in the Railway project canvas.
2. Navigate to the **Variables** tab.
3. Click **RAW Editor** (or add them one by one) and paste your configuration:

```env
DJANGO_SECRET_KEY=generate-a-strong-random-50-character-secret-key
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=https://*.railway.app,https://*.up.railway.app
PLAYWRIGHT_HEADLESS=true

# Database (Supabase PostgreSQL Connection URL)
DATABASE_URL=postgresql://postgres.your-project:your-password@aws-0-region.pooler.supabase.com:6543/postgres

# Supabase Storage (for scraped CSV artifact uploads)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-service-role-or-anon-key
SUPABASE_STORAGE_BUCKET=results

# MailTester Ninja REST API Verification (optional but recommended)
MAILTESTER_API_KEY=your-mailtester-ninja-api-key
MAILTESTER_CONCURRENCY=2

# Webshare Proxy (optional)
WEBSHARE_PROXY_SERVER=http://proxy-host:proxy-port
WEBSHARE_PROXY_USERNAME=your-webshare-username
WEBSHARE_PROXY_PASSWORD=your-webshare-password
```

> **Tip:** You can generate a secure secret key quickly in Python:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(50))"
> ```

---

## Step 4: Generate a Public Domain on Railway

By default, Railway services do not have a public URL until you generate one:

1. In your service, click the **Settings** tab.
2. Scroll down to the **Networking** section.
3. Click **Generate Domain** (Railway will assign a domain like `adapt-io-backend-production.up.railway.app`).
4. (Optional) If you have a custom domain, you can click **Custom Domain** and attach it here.

---

## Step 5: Verify Your Deployment

Once the deployment status shows **Active** (green checkmark):

1. **Health Check**:
   Open in your browser:
   `https://<your-railway-domain>/api/health/`
   You should see:
   ```json
   {"status": "ok"}
   ```

2. **Interactive Swagger Documentation**:
   Visit the root URL:
   `https://<your-railway-domain>/` (or `/api/docs/`)
   You will see the full Swagger UI where you can test endpoints:
   - `POST /api/tasks/start/`
   - `GET /api/tasks/current/`
   - `GET /api/tasks/{task_id}/results/`
   - `GET /api/tasks/{task_id}/download/`

3. **Check Deploy Logs**:
   In Railway, open the **Deployments** tab and click **View Logs**.
   You should see:
   ```
   ==> Running Django database migrations...
   Operations to perform:
     Apply all migrations: admin, auth, contenttypes, sessions, tasks
   Running migrations:
     No migrations to apply. (or applied)
   ==> Starting Gunicorn on 0.0.0.0:xxxx...
   [INFO] Starting gunicorn 23.0.0
   [INFO] Listening at: http://0.0.0.0:xxxx
   ```

---

## Optional: Deploy via Railway CLI

If you prefer deploying from your terminal instead of the web UI:

1. Install Railway CLI:
   ```powershell
   npm install -g @railway/cli
   ```
2. Login to your account:
   ```powershell
   railway login
   ```
3. Initialize the project:
   ```powershell
   railway init
   ```
4. Link or set environment variables:
   ```powershell
   railway variables --set DJANGO_DEBUG=false
   railway variables --set DJANGO_SECRET_KEY="your-secret-key"
   railway variables --set DATABASE_URL="your-supabase-url"
   ```
5. Deploy:
   ```powershell
   railway up
   ```
6. Generate domain:
   ```powershell
   railway domain
   ```

---

## Troubleshooting & Best Practices

| Issue | Solution |
| :--- | :--- |
| **Out of Memory (OOM) during Playwright scraping** | Playwright Chromium requires sufficient RAM. In Railway service **Settings** -> **Resource Limits**, allocate at least **1 GB - 2 GB** RAM. |
| **Database Connection Timeout** | If using Supabase, ensure you use the **Session Mode** or **Transaction Mode** connection pooler string (port `6543`) rather than direct port `5432`, especially on IPv4 networks. Ensure `?sslmode=require` is present if needed. |
| **CSRF verification failed (HTTP 403)** | `DJANGO_CSRF_TRUSTED_ORIGINS` is configured to automatically allow `https://*.railway.app`. If using a custom domain (e.g. `api.yourdomain.com`), add it to `DJANGO_CSRF_TRUSTED_ORIGINS` in Railway Variables. |
| **Playwright "Target closed" or Browser crashes** | Handled automatically in `scraper/browser.py` using `--no-sandbox` and `--disable-dev-shm-usage`. |
