import httpx
import time
from typing import Optional, Dict

# Farcaster/Lens API endpoints (free, public, no auth required)
FARCASTER_API = "https://api.neynar.com/v2/farcaster/search"
LENS_API = "https://api.lens.dev/v2/publications"

async def check_social_sentiment(token_ticker: str, proposal_title: str) -> Dict[str, any]:
    """
    Queries decentralized social APIs to detect if a narrative is already being shilled.
    Returns: {"is_late": bool, "mention_count": int, "reasoning": str}
    """
    search_terms = [token_ticker.upper(), token_ticker.lower(), proposal_title[:30]]
    total_mentions = 0
    recent_spike = False
    
    async with httpx.AsyncClient() as client:
        for term in search_terms:
            try:
                # Query Farcaster (decentralized Twitter alternative)
                params = {"q": term, "limit": 20}
                headers = {"accept": "application/json"}
                resp = await client.get(FARCASTER_API, params=params, headers=headers, timeout=8.0)
                if resp.status_code == 200:
                    data = resp.json()
                    casts = data.get("result", {}).get("casts", [])
                    # Count mentions from last 60 minutes
                    for cast in casts:
                        timestamp = cast.get("timestamp", 0)
                        if timestamp and (time.time() - timestamp) < 3600:
                            total_mentions += 1
                            if total_mentions >= 5:  # Threshold for "spike"
                                recent_spike = True
                                break
                
                time.sleep(1)  # Rate limit protection
                
            except Exception as e:
                print(f"[SOCIAL] ⚠️ Error querying Farcaster for '{term}': {e}")
                continue
    
    # Determine if we're "late to the party"
    if recent_spike or total_mentions >= 10:
        return {
            "is_late": True,
            "mention_count": total_mentions,
            "reasoning": f"High social volume detected ({total_mentions} mentions in 60min). Narrative already priced in."
        }
    elif total_mentions >= 3:
        return {
            "is_late": False,
            "mention_count": total_mentions,
            "reasoning": f"Moderate social chatter ({total_mentions} mentions). Proceed with caution."
        }
    else:
        return {
            "is_late": False,
            "mention_count": total_mentions,
            "reasoning": f"Low social volume ({total_mentions} mentions). True information asymmetry detected."
        }
