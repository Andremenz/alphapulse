import httpx
import asyncio
from config import settings
from typing import List, Dict

def format_alert(alert: Dict) -> str:
    alert_type = alert.get("type", "").lower()

    if alert_type in ["whale", "whale_buy", "tx"]:
        return (f"🐋 <b>Whale Alert (Base)</b>\nValue: <code>{alert.get('value_eth', 'N/A')} ETH</code>\n"
                f"To: <code>{alert.get('to', 'N/A')[:8]}...{alert.get('to', 'N/A')[-4:]}</code>\nTX: https://basescan.org/tx/{alert.get('tx_hash', '')}")
                
    elif alert_type == "governance":
        ai_action = alert.get("ai_action", "IGNORE")
        ai_score = alert.get("ai_score", 0)
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
            return (
                f"🗳️ <b>Governance {alert['state'].capitalize()}</b>\n"
                f"Space: <code>{alert['space']}</code>\n"
                f"Title: {alert['title'][:60]}...\n"
                f"AI Score: {ai_score}/100 ({ai_action})\n"
                f"<a href='{alert['link']}'>View Proposal</a>"
            )

    elif alert_type == "github_commit":
        ai_action = alert.get("ai_action", "IGNORE")
        ai_score = alert.get("ai_score", 0)
        if ai_action == "SNIPE":
            return (
                f"💻 <b>1% ALPHA DETECTED: Code-First Catalyst</b>\n"
                f"📂 <b>Repo:</b> {alert['repo']}\n"
                f"🔨 <b>Commit:</b> <code>{alert['sha']}</code> by {alert['author']}\n"
                f"📝 <b>Message:</b> <i>{alert['message'][:100]}</i>\n"
                f"🧠 <b>AI Semantic Analysis:</b>\n"
                f" - <b>Sentiment Score:</b> {ai_score}/100\n"
                f" - <b>Reasoning:</b> {alert.get('ai_reasoning', 'N/A')}\n"
                f"🔗 <a href='{alert['link']}'>View Code Change</a>"
            )
        else:
            return (
                f"💻 <b>GitHub Commit</b> ({alert['repo']})\n"
                f"<code>{alert['sha']}</code>: {alert['message'][:60]}...\n"
                f"AI Score: {ai_score}/100 ({ai_action})"
            )

    elif alert_type == "insider_swap":
        return (
            f"🕵️‍♂️ <b>SMART MONEY DETECTED: Insider Accumulation</b>\n"
            f"👤 <b>Wallet:</b> {alert['name']}\n"
            f"💰 <b>Action:</b> Swapped <code>{alert['eth_amount']} ETH</code> for {alert['space']}\n"
            f"🧠 <b>AI Reasoning:</b> Core insider directly buying on DEX router.\n"
            f"🔗 <a href='{alert['link']}'>Track Transaction</a>"
        )

    elif alert_type in ["vesting_release", "vesting"]:
        return (
            f"🔓 <b>Vesting Release</b>\n"
            f"📜 <b>Contract:</b> {alert.get('contract_name', 'N/A')}\n"
            f"💰 <b>Amount:</b> <code>{alert.get('amount_eth', 'N/A')} ETH</code>\n"
            f"👤 <b>Beneficiary:</b> <code>{alert.get('beneficiary', 'N/A')}</code>"
        )
            
    elif alert_type in ["weekly_digest", "digest"]:
        return (f"📊 <b>AlphaPulse Weekly Digest</b>\nTotal Events: <code>{alert.get('total_events', 0)}</code>\n"
                f"Top Activity: <code>{alert.get('top_space', 'N/A')}</code>\nPeriod: {alert.get('period', 'Last 7 Days')}")
                
    elif alert_type in ["intelligence_alert", "intelligence"]:
        return (f"{alert.get('title', '🔍 Intelligence Alert')}\n"
                f" Entity: <code>{alert['entity']}</code>\n"
                f"️ Chain: {alert['chain']} | 💰 Amount: <code>{alert['amount']}</code>\n"
                f" Flags: {alert['flags']}\n"
                f"🔗 <a href='{alert['tx']}'>View Transaction</a>")
                
    # Fallback for debugging
    print(f"[TELEGRAM] ⚠️ Unknown alert type: {alert_type}")
    return f"🔔 <b>New Event Detected</b>\nType: <code>{alert_type}</code>\nData: {str(alert)[:150]}..."

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
