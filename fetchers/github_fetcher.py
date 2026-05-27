import httpx
from datetime import datetime
from typing import List, Dict
from fetchers.ai_brain import analyze_code_commit
from fetchers.shadow_ledger import log_snipe_signal
from fetchers.trading_engine import execute_snipe

REPOS = [{"owner": "aerodrome-finance", "repo": "aerodrome-dao", "space": "aerodrome"}, {"owner": "base-org", "repo": "base", "space": "base"}, {"owner": "friendtech", "repo": "friendtech-contracts", "space": "friendtech"}]

async def fetch_github_commits() -> List[Dict]:
    results = []
    async with httpx.AsyncClient() as client:
        for t in REPOS:
            url = f"https://api.github.com/repos/{t['owner']}/{t['repo']}/commits?per_page=3"
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AlphaPulse-Bot"}
            try:
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code != 200: continue
                for c in resp.json():
                    sha = c.get("sha", "")[:7]
                    msg = c.get("commit", {}).get("message", "No message")
                    author = c.get("commit", {}).get("author", {}).get("name", "Unknown")
                    ai = await analyze_code_commit(t['repo'], msg, "")
                    if ai.get("action") == "SNIPE":
                        score = ai.get("narrative_score", 85)
                        await log_snipe_signal({"id": f"github_{sha}", "space": t['space'], "title": f"GitHub: {msg[:50]}", "ai_score": score, "ai_reasoning": ai.get("reasoning", "N/A")})
                        await execute_snipe(t['space'], msg, score)
                    results.append({"id": f"github_{sha}", "type": "github_commit", "repo": t['repo'], "space": t['space'], "sha": sha, "message": msg, "author": author, "link": c.get("html_url", ""), "timestamp": datetime.utcnow().isoformat(), "ai_score": ai.get("narrative_score", 0), "ai_action": ai.get("action", "IGNORE"), "ai_reasoning": ai.get("reasoning", "N/A")})
            except Exception as e: print(f"[GITHUB] Error {t['repo']}: {e}")
    return results
