# PLM SaaS Platform - Deployment to Render

## What You're Deploying

A complete SaaS platform that:
- Onboards 50+ startups
- Generates custom training data for each
- Manages model creation
- Provides admin dashboard

**Cost:** FREE on Render

---

## Step 1: Prepare Files

Your files are ready in `D:\cmp\Plm\saas\`:
- `api.py` - FastAPI backend
- `multi_tenant.py` - Multi-tenant system
- `startup_generator.py` - Data generation
- `dashboard.html` - Admin dashboard
- `requirements.txt` - Dependencies

---

## Step 2: Deploy to Render

### A. Create Render Account
1. Go to https://render.com
2. Sign up with your email
3. Verify email

### B. Create New Web Service
1. Click "New +" → "Web Service"
2. Connect your GitHub/GitLab (or use manual deploy)
3. Or: Use "Deploy from Docker"

### C. Configuration

**Build Command:**
```bash
pip install -r saas/requirements.txt
```

**Start Command:**
```bash
cd saas && uvicorn api:app --host 0.0.0.0 --port $PORT
```

**Environment Variables:**
```
GROQ_API_KEY=your_groq_api_key
SAMBANOVA_API_KEY=your_sambanova_api_key
GEMINI_API_KEY=your_gemini_api_key
```

**Instance Type:** Free

---

## Step 3: Using Your Render API Key

You provided: `rnd_TsYfyDVt8bsAuDac0uEk1ANCTe6N`

This is used for API authentication (if needed later).

---

## Step 4: Access Your Platform

Once deployed:
- **API URL:** `https://your-app-name.onrender.com`
- **Dashboard:** `https://your-app-name.onrender.com/dashboard.html`
- **API Docs:** `https://your-app-name.onrender.com/docs`

---

## Alternative: Deploy to Vercel

Vercel token: `TiHrdYBy56EVBhrbGEpV2sJW`

### Using Vercel CLI:

```bash
# Install Vercel CLI
npm install -g vercel

# Login with token
vercel login --token TiHrdYBy56EVBhrbGEpV2sJW

# Deploy
cd D:\cmp\Plm\saas
vercel deploy --prod
```

**Note:** Vercel is better for frontend. Use Render for full backend + API.

---

## Step 5: Test Deployment

```bash
# Test API
curl https://your-app.onrender.com/health

# Test stats
curl https://your-app.onrender.com/stats

# Onboard a startup
curl -X POST https://your-app.onrender.com/startups \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Startup", "niche": "Tech", "topics": ["AI", "Web3"]}'
```

---

## Step 6: Start Onboarding Startups!

1. Open dashboard: `https://your-app.onrender.com/dashboard.html`
2. Fill in startup details
3. Click "Onboard Startup"
4. Click "Generate Data" for each startup
5. Download training data
6. Send to startup with training instructions

---

## Scaling

### Free Tier Limits:
- 750 hours/month (enough for 24/7)
- 512 MB RAM
- Sleeps after 15 min inactivity

### Upgrade to Paid ($7/month):
- Always on
- 512 MB → 2 GB RAM
- Custom domain

---

## Monitoring

Check logs in Render dashboard:
- Go to your service
- Click "Logs"
- Watch real-time generation

---

## Backup & Data

All startup data stored in:
- `./workspaces/{startup_id}/`
- `./clients.json`

**Backup regularly:**
```bash
# Download from Render
render ps:copy files:. ./backup/
```

---

## Next Steps

1. Deploy to Render (5 minutes)
2. Test with 1-2 test startups
3. Start onboarding real startups
4. Generate their models
5. Charge them $500-5000 each!

**Your $100k business starts now!**
