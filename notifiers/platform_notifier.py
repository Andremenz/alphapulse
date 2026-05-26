import httpx
import asyncio
from config import settings
from typing import List, Dict

def format_alert(alert: Dict) -> str:
    if alert["type"] == "whale_buy":
        return (f"🐋 <b>Whale Alert (Base)</b>\nValue: <code>{alert['value_eth']:.4f} ETH</code>\n"
                f"To: <code>{alert['to'][:8]}...{alert['to'][-4:]}</code>\nTX: https://basescan.org/tx/{alert['tx_hash']}")
                
    elif alert["type"] == "governance":
        ai_action = alert.get("ai_action", "IGNORE")
        ai_score = alert.get("ai_score", 0)
        
        # 🚨 THE 1% ALPHA FORMAT 🚨
        if ai_action == "SNIPE":
            return (
                f"🚨 <b>1% ALPHA DETECTED: Information Asymmetry</b>\n"
                f"🗳️ <b>Source:</b> Snapshot Governance ({alert['space']})\n"
                f"📜 <b>Event:</b> {alert['title'][:100]}...\n"
                f"🧠 <b>AI Semantic Analysis:</b>\n"
                f" - <b>Sentiment Score:</b> {ai_score}/100\n"
                f" - <b>FOMO Potential:</b> {alert.get('ai_fomo', 'High')}\n"
                f" - <b>Reasoning:</b> <i>{alert.get('ai_reasoning', 'N/A')}</i>\n"
                f"🎯 <b>Actionable Extraction:</b>\n"
                f" - <b>Status:</b> {alert['state'].upper()} (Market Awareness: Low)\n"
                f"🔗 <a href='{alert['link']}'>Read Raw Proposal</a>"
            )
        else:
            # Standard format for MONITOR or IGNORE
            return (
                f"🗳️ <b>Governance {alert['state'].capitalize()}</b>\n"
                f"Space: <code>{alert['space']}</code>\n"
                f"Title: {alert['title'][:60]}...\n"
                f"AI Score: {ai_score}/100 ({ai_action})\n"
                f"<a href='{alert['link']}'>View Proposal</a>"
            )
            
    elif alert["type"] == "weekly_digest":
        return (f"📊 <b>AlphaPulse Weekly Digest</b>\nTotal Events: <code>{alert.get('total_events', 0)}</code>\n"
                f"Top Activity: <code>{alert.get('top_space', 'N/A')}</code>\nPeriod: {alert.get('period', 'Last 7 Days')}")
                
    elif alert["type"] == "intelligence_alert":
        return (f"{alert.get('title', '🔍 Intelligence Alert')}\n"
                f" Entity: <code>{alert['entity']}</code>\n"
                f"️ Chain: {alert['chain']} | 💰 Amount: <code>{alert['amount']}</code>\n"
                f" Flags: {alert['flags']}\n"
                f"🔗 <a href='{alert['tx']}'>View Transaction</a>")
                
    return "🔔 Unknown event type"

async def send_notifications(alerts: List[Dict]):
    if not alerts: return

    creds = settings.get_notifier_creds()
    url = f"https://api.telegram.org/bot{creds['bot_token']}/sendMessage"
    payload_base = {"chat_id": creds["chat_id"], "parse_mode": "HTML"}

    async with httpx.AsyncClient(timeout=15) as client:
        if settings.platform == "telegram":
            for i, alert in enumerate(alerts[:3]):
                text = format_alert(alert)
                try:
                    resp = await client.post(url, json={**payload_base, "text": text})
                    status = "✅" if resp.status_code == 200 else "❌"
                    print(f"[TELEGRAM] {status} Alert {i+1} | {resp.status_code}")
                except Exception as e:
                    print(f"[TELEGRAM] ❌ Network error: {e}")
                await asyncio.sleep(1)
                
        elif settings.platform == "discord":
            await client.post(creds["webhook_url"], json={"content": "\n\n".join([format_alert(a) for a in alerts[:3]])})
