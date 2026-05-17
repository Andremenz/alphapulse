import httpx
import asyncio
from config import settings
from typing import List, Dict

def format_alert(alert: Dict) -> str:
    """Formats alert to safe HTML under 4000 chars."""
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
            f"Title: {alert['title'][:60]}...\n"
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

    creds = settings.get_notifier_creds()
    url = f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage"
    payload_base = {"chat_id": creds["chat_id"], "parse_mode": "HTML"}

    async with httpx.AsyncClient(timeout=15) as client:
        if settings.platform == "telegram":
            # Send max 3 most recent alerts to avoid spam & length limits
            for i, alert in enumerate(alerts[:3]):
                text = format_alert(alert)
                payload = {**payload_base, "text": text}

                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        print(f"[TELEGRAM] ✅ Alert {i+1} delivered successfully.")
                    else:
                        print(f"[TELEGRAM] ❌ Alert {i+1} failed: {resp.status_code} | {resp.text}")
                except Exception as e:
                    print(f"[TELEGRAM] ❌ Network error: {e}")

                # 1-second delay between messages to avoid rate limits
                await asyncio.sleep(1)

        elif settings.platform == "discord":
            await client.post(
                creds["webhook_url"],
                json={"content": "\n\n".join([format_alert(a) for a in alerts[:3]])}
            )
        else:
            print(f"[DRY RUN] Platform '{settings.platform}' not configured.")
