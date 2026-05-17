import httpx
from config import settings
from typing import List, Dict

def format_alert(alert: Dict) -> str:
    """Converts raw alert dict to HTML text compatible with both platforms."""
    if alert["type"] == "whale_buy":
        return (
            f"🐋 <b>Whale Alert (Base)</b>\n"
            f"Value: <code>{alert['value_eth']:.4f} ETH</code>\n"
            f"To: <code>{alert['to'][:8]}...{alert['to'][-4:]}</code>\n"
            f"TX: https://basescan.org/tx/{alert['tx_hash']}"
        )
    elif alert["type"] == "governance":
        return (
            f"🗳️ <b>Governance Closed</b>\n"
            f"Space: <code>{alert['space']}</code>\n"
            f"Title: {alert['title']}\n"
            f"Votes: <code>{alert['votes']}</code>\n"
            f"<a href='{alert['link']}'>View Proposal</a>"
        )
    elif alert["type"] == "weekly_digest":
        return (
            f"📊 <b>AlphaPulse Weekly Digest</b>\n"
            f"Total Events: <code>{alert.get('total_events', 0)}</code>\n"
            f"Top Activity: <code>{alert.get('top_space', 'N/A')}</code>\n"
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
            url = f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage"
            payload = {"chat_id": creds["chat_id"], "text": combined, "parse_mode": "HTML"}
            
            # DEBUG: Send request and print Telegram's response
            resp = await client.post(url, json=payload)
            print(f"[TELEGRAM] Status: {resp.status_code}")
            print(f"[TELEGRAM] Response: {resp.text}")
            
            if resp.status_code != 200:
                print(f"[TELEGRAM] ❌ ERROR: Telegram rejected the message.")
            else:
                print(f"[TELEGRAM] ✅ Message delivered successfully.")

        elif settings.platform == "discord":
            await client.post(
                creds["webhook_url"],
                json={"content": combined}
            )
        else:
            print(f"[DRY RUN] Platform '{settings.platform}' not configured.")
