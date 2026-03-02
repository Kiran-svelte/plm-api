#!/bin/bash
# PLM Enterprise - Automated Deployment Script
# Run this on your local machine

set -e

echo "=========================================="
echo " PLM ENTERPRISE - AUTOMATED DEPLOYMENT"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Deploy Backend to Render
echo -e "${BLUE}[1/3] Deploying Backend to Render...${NC}"
echo ""
echo "Go to: https://dashboard.render.com/create?type=web"
echo ""
echo "Configuration:"
echo "  - Connect Repository: Kiran-svelte/PLM"
echo "  - Name: plm-api"
echo "  - Branch: main"
echo "  - Root Directory: enterprise"
echo "  - Runtime: Python 3"
echo "  - Build Command: pip install -r requirements.txt"
echo "  - Start Command: uvicorn backend.api:app --host 0.0.0.0 --port \$PORT"
echo ""
echo "Environment Variables:"
echo "  SUPABASE_URL=your_supabase_url"
echo "  SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key"
echo "  GROQ_API_KEY=your_groq_api_key"
echo "  SAMBANOVA_API_KEY=your_sambanova_api_key"
echo "  GEMINI_API_KEY=your_gemini_api_key"
echo "  ENVIRONMENT=production"
echo ""
read -p "Press Enter when backend is deployed and copy your Render URL..."
echo ""

# Get Render URL
read -p "Enter your Render backend URL (e.g., https://plm-api.onrender.com): " BACKEND_URL
echo ""

# Step 2: Deploy Frontend to Vercel
echo -e "${BLUE}[2/3] Deploying Frontend to Vercel...${NC}"
echo ""
echo "Go to: https://vercel.com/new"
echo ""
echo "Configuration:"
echo "  - Import: Kiran-svelte/PLM"
echo "  - Framework: Next.js"
echo "  - Root Directory: frontend"
echo "  - Build Command: npm run build"
echo ""
echo "Environment Variables:"
echo "  NEXT_PUBLIC_API_URL=$BACKEND_URL"
echo "  NEXT_PUBLIC_SUPABASE_URL=https://hksgkdhesjcbuklsrlmo.supabase.co"
echo "  NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imhrc2drZGhlc2pjYnVrbHNybG1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzEwNTk4MDYsImV4cCI6MjA4NjYzNTgwNn0.He8_KpvR4wP4sECGyQZxyEt94oVexAa1y3HfbNl-wDA"
echo ""
read -p "Press Enter when frontend is deployed and copy your Vercel URL..."
echo ""

# Get Vercel URL
read -p "Enter your Vercel frontend URL (e.g., https://plm-enterprise.vercel.app): " FRONTEND_URL
echo ""

# Step 3: Test Deployment
echo -e "${BLUE}[3/3] Testing Deployment...${NC}"
echo ""

echo "Testing backend health..."
curl -s "$BACKEND_URL/health" | python3 -m json.tool || echo "Backend not ready yet (may take 2-3 minutes)"
echo ""

echo "=========================================="
echo -e "${GREEN}DEPLOYMENT COMPLETE!${NC}"
echo "=========================================="
echo ""
echo "Your Deployed System:"
echo "  Frontend: $FRONTEND_URL"
echo "  Backend:  $BACKEND_URL"
echo "  API Docs: $BACKEND_URL/docs"
echo ""
echo "Next Steps:"
echo "  1. Open: $FRONTEND_URL"
echo "  2. Test the dashboard"
echo "  3. Create your first organization"
echo ""
echo "Start selling to customers! 🚀"
