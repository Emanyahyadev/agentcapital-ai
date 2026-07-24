#!/usr/bin/env bash
# One-command demo bring-up: local API + public Cloudflare tunnel + frontend
# redeploy pointed at the fresh tunnel URL.
#
# Quick tunnels get a new URL on every start, so the Vercel env var must be
# refreshed each session. Requires VERCEL_TOKEN in the environment
# (create at vercel.com/account/settings/tokens).

set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/4] starting API on :8000..."
(cd backend && uv run uvicorn src.api.main:app --port 8000 >/tmp/agentcapital_api.log 2>&1 &)
sleep 6
curl -sf http://localhost:8000/health >/dev/null || { echo "API failed to start — see /tmp/agentcapital_api.log"; exit 1; }

echo "[2/4] opening Cloudflare tunnel..."
cloudflared tunnel --url http://localhost:8000 >/tmp/agentcapital_tunnel.log 2>&1 &
sleep 10
URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/agentcapital_tunnel.log | head -1)
[ -n "$URL" ] && echo "    backend public URL: $URL" || { echo "tunnel failed — see /tmp/agentcapital_tunnel.log"; exit 1; }

echo "[3/4] pointing the Vercel frontend at the tunnel..."
cd frontend
npx -y vercel env rm NEXT_PUBLIC_API_URL production --yes --token "$VERCEL_TOKEN" >/dev/null 2>&1 || true
printf "%s" "$URL" | npx -y vercel env add NEXT_PUBLIC_API_URL production --token "$VERCEL_TOKEN" >/dev/null

echo "[4/4] redeploying frontend..."
npx -y vercel deploy --prod --yes --token "$VERCEL_TOKEN" 2>&1 | grep -oE "https://agentcapital-[a-z0-9-]+\.vercel\.app" | head -1 || true

echo
echo "demo ready:"
echo "  dashboard : https://agentcapital-ai.vercel.app"
echo "  api       : $URL"
