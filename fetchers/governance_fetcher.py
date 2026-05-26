import httpx
from datetime import datetime
from typing import List, Dict
from config import settings
from fetchers.ai_brain import analyze_alpha_event

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
    """Queries Snapshot GraphQL for active proposals and runs them through the AI Brain."""
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
              # Run AI Brain on the title and body
        ai_analysis = await analyze_alpha_event(p["title"], p.get("body", "No description provided."))
        
        # 🚨 NEW: Log SNIPE signals to the Shadow Ledger
        if ai_analysis.get("action") == "SNIPE":
            from fetchers.shadow_ledger import log_snipe_signal
            proposal_data = {
                "id": p["id"],
                "space": space,
                "title": p["title"],
                "ai_score": ai_analysis.get("narrative_score", 0),
                "ai_reasoning": ai_analysis.get("reasoning", "N/A")
            }
            await log_snipe_signal(proposal_data)

        results.append({
