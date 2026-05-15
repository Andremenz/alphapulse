import httpx
from datetime import datetime
from typing import List, Dict
from config import settings

GOV_QUERY = """
query GetProposals($space: String!, $first: Int!, $skip: Int!) {
  proposals(
    first: $first
    skip: $skip
    where: { state: "closed", space_in: [$space] }
    orderBy: "created"
    orderDirection: desc
  ) {
    id
    title
    state
    link
    votes
    author
  }
}
"""

async def fetch_snapshot_governance(space: str, first: int = 5) -> List[Dict]:
    """Queries Snapshot GraphQL for recently closed proposals on a DAO space."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://hub.snapshot.org/graphql",
            json={"query": GOV_QUERY, "variables": {"space": space, "first": first, "skip": 0}}
        )
        resp.raise_for_status()
        data = resp.json()
        
    proposals = data.get("data", {}).get("proposals", [])
    return [{
        "type": "governance",
        "space": space,
        "title": p["title"],
        "state": p["state"],
        "votes": p["votes"],
        "link": f"https://snapshot.org/#/{space}/proposal/{p['id']}",
        "timestamp": datetime.utcnow().isoformat()
    } for p in proposals]
