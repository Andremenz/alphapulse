import httpx
from datetime import datetime
from typing import List, Dict
from fetchers.ai_brain import analyze_code_commit
from fetchers.shadow_ledger import log_snipe_signal
from fetchers.trading_engine import execute_snipe

# Target Repos (Owner, Repo Name, and the mapped Snapshot Space for trading)
# Verified active Base ecosystem repositories
REPOS = [
    {"owner": "aerodrome-finance", "repo": "aerodrome-dao", "space": "aerodrome"},
    {"owner": "base-org", "repo": "base", "space": "base"},
    {"owner": "friendtech", "repo": "friendtech-contracts", "space": "friendtech"},
]

async def fetch_github_commits() -> List[Dict]:
    results = []
    async with httpx.AsyncClient() as client:
        for target in REPOS:
            owner = target["owner"]
            repo = target["repo"]
            space = target["space"]
            url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=3"
            headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AlphaPulse-Bot"}

            try:
                resp = await client.get(url, headers=headers, timeout=10.0)
                if resp.status_code != 200:
                    print(f"[GITHUB] Rate limit or error for {repo}: {resp.status_code}")
                    continue
                commits = resp.json()

                for c in commits:
                    sha = c.get("sha", "")[:7]
                    message = c.get("commit", {}).get("message", "No message")
                    author = c.get("commit", {}).get("author", {}).get("name", "Unknown")
                    link = c.get("html_url", "")

                    # Run AI Brain on the commit
                    ai_data = await analyze_code_commit(repo, message, "")

                    if ai_data.get("action") == "SNIPE":
                        proposal_data = {
                            "id": f"github_{sha}",
                            "space": space,
                            "title": f"GitHub Commit: {message[:50]}",
                            "ai_score": ai_data.get("narrative_score", 0),
                            "ai_reasoning": ai_data.get("reasoning", "N/A")
                        }
                        await log_snipe_signal(proposal_data)
                        await execute_snipe(space, message)

                    results.append({
                        "id": f"github_{sha}",
                        "type": "github_commit",
                        "repo": repo,
                        "space": space,
                        "sha": sha,
                        "message": message,
                        "author": author,
                        "link": link,
                        "timestamp": datetime.utcnow().isoformat(),
                        "ai_score": ai_data.get("narrative_score", 0),
                        "ai_action": ai_data.get("action", "IGNORE"),
                        "ai_reasoning": ai_data.get("reasoning", "N/A")
                    })
            except Exception as e:
                print(f"[GITHUB] Error fetching {owner}/{repo}: {e}")
    return results
