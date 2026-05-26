import httpx
from datetime import datetime
from typing import List, Dict
from config import settings
from fetchers.ai_brain import analyze_alpha_event
from fetchers.shadow_ledger import log_snipe_signal
from fetchers.trading_engine import execute_snipe

GOV_QUERY = """
query GetProposals($space: String!, $first: Int!, $skip: Int!) {
  proposals(
    first: $first
    skip: $skip
    where: { state: "active", space_in: [$space] }
    orderBy: "created"
    orderDirection: desc
  ) {
    id
    title
    body
    state
    link
    votes
    author
  }
}
"""

async def fetch_snapshot_governance(space: str, first: int=5) -> List[Dict]:
    """Queries Snapshot, runs AI Brain, logs to Ledger, and Executes Snipe."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://hub.snapshot.org/graphql",
            json={"query": GOV_QUERY, "variables": {"space": space, "first": first, "skip": 0}}
        )
        resp.raise_for_status()
        data = resp.json()
        
    proposals = data.get("data", {}).get("proposals", [])
    results = []
    
    for p in proposals:
        ai_analysis = await analyze_alpha_event(p["title"], p.get("body", "No description provided."))
        
        if ai_analysis.get("action") == "SNIPE":
            proposal_data = {
                "id": p["id"],
                "space": space,
                "title": p["title"],
                "ai_score": ai_analysis.get("narrative_score", 0),
                "ai_reasoning": ai_analysis.get("reasoning", "N/A")
            }
            # 1. Log to Shadow Ledger
            await log_snipe_signal(proposal_data)
            
            # 2. 🚨 EXECUTE THE TRADE 🚨
            await execute_snipe(space, p["title"])

        results.append({
            "id": p["id"],
            "type": "governance",
            "space": space,
            "title": p["title"],
            "body": p.get("body", ""),
            "state": p["state"],
            "votes": p["votes"],
            "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}",
            "timestamp": datetime.utcnow().isoformat(),
            "ai_score": ai_analysis.get("narrative_score", 0),
            "ai_action": ai_analysis.get("action", "IGNORE"),
            "ai_reasoning": ai_analysis.get("reasoning", "N/A"),
            "ai_fomo": ai_analysis.get("fomo_potential", "Low")
        })
        
    return results
