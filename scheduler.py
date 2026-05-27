import asyncio
import json
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings
from database import state_db
from fetchers.whale_fetcher import fetch_recent_whale_transfers
from fetchers.governance_fetcher import fetch_snapshot_governance
from fetchers.intelligence_fetcher import run_intelligence_scan
from fetchers.exit_manager import check_and_execute_exits
from fetchers.gas_monitor import check_gas_health
from reporters.pdf_reporter import generate_pdf
from notifiers.platform_notifier import send_notifications

scheduler = AsyncIOScheduler()
LAST_UPDATE_ID = 0

async def run_task(config_name: str, config: dict):
    print(f"[{config_name}]  Starting check...")
    try:
        now_ts = int(datetime.utcnow().timestamp())
        last_ts, seen_ids = await state_db.get_last_state(config_name)
        print(f"[{config_name}] Last check: {last_ts}, Seen IDs: {len(seen_ids)}")
        new_alerts = []
        if config["type"] == "whale":
            alerts = await fetch_recent_whale_transfers(config.get("threshold_eth", 10.0))
        elif config["type"] == "governance":
            alerts = await fetch_snapshot_governance(config["space"])
        elif config_name == "githubwatch":
            from fetchers.github_fetcher import fetch_github_commits
            alerts = await fetch_github_commits()
        elif config["type"] == "digest":
            alerts = [{"type": "weekly_digest", "total_events": len(seen_ids), "top_space": config.get("space", "N/A"), "period": "7d"}]
        elif config["type"] == "vesting":
            from fetchers.vesting_fetcher import fetch_vesting_releases
            alerts = []
            for contract in config.get("contracts", []): alerts.extend(await fetch_vesting_releases(contract["address"], contract.get("chain", "base")))
        elif config["type"] == "intelligence":
            from fetchers.vesting_fetcher import fetch_vesting_releases
            vesting_data = []
            for contract in config.get("contracts", []): vesting_data.extend(await fetch_vesting_releases(contract["address"], contract.get("chain", "ethereum")))
            alerts = await run_intelligence_scan(vesting_data, config)
            if alerts: generate_pdf(alerts, config.get("report_output_dir", "./reports"))
        elif config["type"] == "solana_monitor":
            from fetchers.solana_fetcher import fetch_solana_vesting_transfers
            alerts = []
            for prog in config.get("programs", []): alerts.extend(await fetch_solana_vesting_transfers(prog["address"]))
        else: return

        for a in alerts:
            aid = a.get("tx_hash") or a.get("tx") or a.get("id") or a.get("title") or a.get("sha")
            if aid and aid not in seen_ids: new_alerts.append(a); seen_ids.append(aid); seen_ids = seen_ids[-100:]

        if new_alerts:
            await send_notifications(new_alerts)
            await state_db.update_state(config_name, now_ts, seen_ids)
        else: print(f"[{config_name}]  No new data.")
    except Exception as e: print(f"[{config_name}]  ERROR: {str(e)}")

async def run_insider_watch():
    print("[INSIDER_WATCH] Starting check...")
    new_alerts = []
    from fetchers.insider_fetcher import check_insider_wallets
    async for alert in check_insider_wallets(): new_alerts.append(alert)
    if new_alerts: await send_notifications(new_alerts)
    else: print("[INSIDER_WATCH]  No new data.")

async def run_gas_check():
    print("[GAS_MONITOR] Starting health check...")
    new_alerts = []
    async for alert in check_gas_health(): new_alerts.append(alert)
    if new_alerts: await send_notifications(new_alerts)
    else: print("[GAS_MONITOR]  No new data.")

async def check_telegram_commands():
    global LAST_UPDATE_ID
    creds = settings.get_notifier_creds()
    url = f"https://api.telegram.org/bot{creds['bot_token']}/getUpdates?offset={LAST_UPDATE_ID + 1}&limit=5"
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for upd in updates:
                    msg = upd.get("message", {})
                    text = msg.get("text", "")
                    LAST_UPDATE_ID = upd["update_id"]
                    if text.startswith("/approve "):
                        pid = text.split("/approve ")[1].strip()
                        try:
                            with open("data/pending_proposals.json", "r") as f: pending = json.load(f)
                            for p in pending:
                                if p["id"] == pid:
                                    p["status"] = "APPROVED"
                                    with open("data/active_prompts.json", "r") as f: prompts = json.load(f)
                                    prompts[p["type"]] = p["new_prompt"]
                                    with open("data/active_prompts.json", "w") as f: json.dump(prompts, f, indent=2)
                                    with open("data/pending_proposals.json", "w") as f: json.dump(pending, f, indent=2)
                                    print(f"[PROMPT] ✅ Approved & Applied: {pid}")
                                    break
                        except Exception as e: print(f"[PROMPT] ❌ Approval error: {e}")
                    elif text.startswith("/reject "):
                        pid = text.split("/reject ")[1].strip()
                        try:
                            with open("data/pending_proposals.json", "r") as f: pending = json.load(f)
                            for p in pending:
                                if p["id"] == pid: p["status"] = "REJECTED"
                            with open("data/pending_proposals.json", "w") as f: json.dump(pending, f, indent=2)
                            print(f"[PROMPT] ❌ Rejected: {pid}")
                        except: pass
        except: pass

def setup_scheduler():
    configs = settings.load_example_configs()
    for name, cfg in configs.items():
        scheduler.add_job(run_task, "interval", args=[name, cfg], minutes=settings.check_interval_minutes, id=name, replace_existing=True, max_instances=1)
    try:
        solana_config = settings.load_config("solana_watch")
        if solana_config: scheduler.add_job(run_task, "interval", args=["solana_watch", solana_config], minutes=solana_config.get("check_interval_minutes", 10), id="solana_watch", replace_existing=True, max_instances=1)
    except: pass
    scheduler.add_job(check_and_execute_exits, "interval", minutes=5, id="exit_manager", replace_existing=True, max_instances=1)
    scheduler.add_job(run_task, "interval", args=["githubwatch", {"type": "github"}], minutes=15, id="githubwatch", replace_existing=True, max_instances=1)
    scheduler.add_job(run_insider_watch, "interval", minutes=10, id="insider_watch", replace_existing=True, max_instances=1)
    scheduler.add_job(run_gas_check, "interval", minutes=30, id="gas_monitor", replace_existing=True, max_instances=1)
    scheduler.add_job(check_telegram_commands, "interval", seconds=30, id="prompt_listener", replace_existing=True, max_instances=1)
    print("⏱️ Prompt Listener loaded (checking for /approve or /reject every 30s).")
    print(f"⏱️ Scheduler loaded with {len(configs) + 5} tasks.")
