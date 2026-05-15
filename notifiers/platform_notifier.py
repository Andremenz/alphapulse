import httpx
from config import settings
from typing import List, Dict

def format_alert(alert: Dict) -> str:
    """Converts raw alert dict to markdown text compatible with both platforms."""
    if alert["type"] == "whale_buy":
        return (
            f"🐋 **Whale Alert (Base)**\n"
            f"Value: `{alert['value_eth']:.2f} ETH`\n"
            f"To: `{alert['to'][:6]}...{alert['to'][-4:]}`\n"
            f"TX: https://basescan.org/tx/{alert['tx_hash']}"
        )
    elif alert["type"] == "governance":
        return (
            f"🗳️ **Governance Closed**\n"
            f"Space: `{alert['space']}`\n"
            f"Title: {alert['title']}\n"
            f"Votes: `{alert['votes']}`\n"
            f"[View Proposal]({alert['link']})"
        )
    elif alert["type"] == "weekly_digest":
        return (
            f"📊 **AlphaPulse Weekly Digest**\n"
            f"Total Events: `{alert.get('total_events', 0)}`\n"
            f"Top Activity: `{alert.get('top_space', 'N/A')}`\n"
            f"Period: {alert.get('period', 'Last 7 Days')}"
        )
    return "🔔 Unknown event type"

async def send_notifications(alerts: List[Dict]):
    if not alerts:
        return
        
    texts = [format_alert(a) for a in alerts]
    combined = "\n\n---\n\n".join(texts)
    
    creds = settings.get_notifier_creds()
    async with httpx.AsyncClient(timeout=15) as client:
        if settings.platform == "telegram":
            await client.post(
                f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage",
                json={"chat_id": creds["chat_id"], "text": combined, "parse_mode": "Markdown"}
            )
        elif settings.platform == "discord":
            await client.post(
                creds["webhook_url"],
                json={"content": combined}
            )
        else:
            print(f"[DRY RUN] Platform '{settings.platform}' not configured. Message skipped.")
