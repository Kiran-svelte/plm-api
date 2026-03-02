# 🚀 DEPLOY IN 5 MINUTES - COPY/PASTE GUIDE

## STATUS UPDATE
✅ Database: DEPLOYED (you did this)
✅ Backend Code: On GitHub
✅ Frontend Code: On GitHub
⏳ Backend Deployment: 2 minutes (your action needed)
⏳ Frontend Deployment: 2 minutes (your action needed)

---

## STEP 1: Deploy Backend (2 minutes)

### Go to: https://dashboard.render.com/create?type=web

### Click these buttons:
1. **"Connect Repository"** → Select: `Kiran-svelte/PLM`
2. **"Connect"**

### Fill in this form:
```
Name: plm-api
Branch: main
Root Directory: enterprise
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: uvicorn backend.api:app --host 0.0.0.0 --port $PORT
Instance Type: Free
```

### Click **"Advanced"** and add Environment Variables:

Copy-paste these EXACTLY:
```
SUPABASE_URL
your_supabase_url

SUPABASE_SERVICE_ROLE_KEY
your_supabase_service_role_key

GROQ_API_KEY
your_groq_api_key

SAMBANOVA_API_KEY
your_sambanova_api_key

GEMINI_API_KEY
your_gemini_api_key

ENVIRONMENT
production
```

### Click **"Create Web Service"**

⏳ Wait 3-5 minutes for deployment...

### ✅ When done, COPY YOUR URL (looks like: `https://plm-api-XXXX.onrender.com`)

---

## STEP 2: Deploy Frontend (2 minutes)

### Go to: https://vercel.com/new

### Click these buttons:
1. **"Import Git Repository"**
2. Select: `Kiran-svelte/PLM`
3. **"Import"**

### Configure Project:
```
Framework Preset: Next.js
Root Directory: frontend (click "Edit" to change from ./)
Build Command: npm run build
Output Directory: .next
Install Command: npm install
```

### Add Environment Variables:

**IMPORTANT:** Replace `YOUR_RENDER_URL` with the URL you copied from Step 1!

```
NEXT_PUBLIC_API_URL
YOUR_RENDER_URL_HERE

NEXT_PUBLIC_SUPABASE_URL
https://hksgkdhesjcbuklsrlmo.supabase.co

NEXT_PUBLIC_SUPABASE_ANON_KEY
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhrc2drZGhlc2pjYnVrbHNybG1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEwNTk4MDYsImV4cCI6MjA4NjYzNTgwNn0.He8_KpvR4wP4sECGyQZxyEt94oVexAa1y3HfbNl-wDA
```

### Click **"Deploy"**

⏳ Wait 2-3 minutes for deployment...

### ✅ When done, COPY YOUR URL (looks like: `https://plm-enterprise-XXXX.vercel.app`)

---

## STEP 3: Test Your Deployment

### Test Backend:
```bash
curl https://YOUR-RENDER-URL/health
```
Should return: `{"status":"healthy",...}`

### Test Frontend:
Open: `https://YOUR-VERCEL-URL`
You should see the landing page!

### Test API Docs:
Open: `https://YOUR-RENDER-URL/docs`
You should see Swagger UI!

---

## 🎉 YOU'RE DEPLOYED!

**Your System:**
- 🌐 Frontend: `https://YOUR-VERCEL-URL`
- 🔌 Backend: `https://YOUR-RENDER-URL`
- 📚 API Docs: `https://YOUR-RENDER-URL/docs`

**Now:**
1. Go to your frontend URL
2. Click "Dashboard"
3. System is ready to use!

---

## WHY I CAN'T DEPLOY FOR YOU

**The APIs require:**
- ❌ Render: Needs payment info (even for free tier, first deployment)
- ❌ Vercel: Needs GitHub connection in dashboard (can't do via API)

**So you must:**
- ✅ Click "Deploy" buttons in dashboards (2 minutes each)
- ✅ Copy/paste the configs above
- ✅ That's it!

**I've done everything else. Just click 2 buttons.** 🎯
