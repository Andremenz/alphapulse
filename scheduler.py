import asyncio
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

async def run_task(config_name: str, config: dict):
    print(f"[{config_name}]  Starting check...")
    try:
        now_ts = int(datetime.utcnow().timestamp())
        last_ts, seen_ids = await state_db.get_last_state(config_name)
        print(f"[{config_name}] Last check: {last_ts}, Seen IDs: {len(seen_ids)}")
        
        new_alerts = []
        
        if config["type"] == "whale":
            print(f"[{config_name}] Fetching whale transfers...")
            alerts = await fetch_recent_whale_transfers(config.get("threshold_eth", 10.0))
            print(f"[{config_name}] Found {len(alerts)} raw alerts")
            
        elif config["type"] == "governance":
            print(f"[{config_name}] Fetching governance...")
            alerts = await fetch_snapshot_governance(config["space"])
            print(f"[{config_name}] Found {len(alerts)} gov events")

        elif config_name == "githubwatch":
            print(f"[{config_name}] Fetching GitHub commits...")
            from fetchers.github_fetcher import fetch_github_commits
            alerts = await fetch_github_commits()
            print(f"[{config_name}] Found {len(alerts)} GitHub events")
            
        elif config["type"] == "digest":
            alerts = [{"type": "weekly_digest", "total_events": len(seen_ids), "top_space": config.get("space", "N/A"), "period": "7d"}]
            
        elif config["type"] == "vesting":
            print(f"[{config_name}] Fetching vesting releases...")
            from fetchers.vesting_fetcher import fetch_vesting_releases
            all_alerts = []
            for contract in config.get("contracts", []):
                all_alerts.extend(await fetch_vesting_releases(contract["address"], contract.get("chain", "base")))
            alerts = all_alerts
            print(f"[{config_name}] Found {len(all_alerts)} vesting releases")

        elif config["type"] == "intelligence":
            print(f"[{config_name}] Running institutional intelligence scan...")
            from fetchers.vesting_fetcher import fetch_vesting_releases
            vesting_data = []
            for contract in config.get("contracts", []):
                vesting_data.extend(await fetch_vesting_releases(contract["address"], contract.get("chain", "ethereum")))
            alerts = await run_intelligence_scan(vesting_data, config)
            if alerts:
                pdf_path = generate_pdf(alerts, config.get("report_output_dir", "./reports"))
                print(f"[{config_name}] 📄 Audit report generated: {pdf_path}")
            print(f"[{config_name}] Found {len(alerts)} intelligence alerts")

        elif config["type"] == "solana_monitor":
            print(f"[{config_name}] Fetching Solana monitoring data...")
            from fetchers.solana_fetcher import fetch_solana_vesting_transfers
            all_alerts = []
            for prog in config.get("programs", []):
                all_alerts.extend(await fetch_solana_vesting_transfers(prog["address"]))
            alerts = all_alerts
            print(f"[{config_name}] Found {len(alerts)} Solana events")
            
        else:
            return

        for a in alerts:
            aid = a.get("tx_hash") or a.get("tx") or a.get("id") or a.get("title") or a.get("sha")
            if aid and aid not in seen_ids:
                new_alerts.append(a)
                seen_ids.append(aid)
                seen_ids = seen_ids[-100:]

        if new_alerts:
            print(f"[{config_name}] 📤 Sending {len(new_alerts)} alerts...")
            await send_notifications(new_alerts)
            await state_db.update_state(config_name, now_ts, seen_ids)
            print(f"[{config_name}] ✅ Sent {len(new_alerts)} new alerts.")
        else:
            print(f"[{config_name}]  No new data.")
            
    except Exception as e:
        print(f"[{config_name}]  ERROR: {str(e)}")

async def run_insider_watch():
    print("[INSIDER_WATCH] Starting check...")
    new_alerts = []
    from fetchers.insider_fetcher import check_insider_wallets
    async for alert in check_insider_wallets():
        new_alerts.append(alert)
    if new_alerts:
        print(f"[INSIDER_WATCH] 📤 Sending {len(new_alerts)} alerts...")
        await send_notifications(new_alerts)
        print(f"[INSIDER_WATCH] ✅ Sent {len(new_alerts)} new alerts.")
    else:
        print("[INSIDER_WATCH]  No new data.")

async def run_gas_check():
    print("[GAS_MONITOR] Starting health check...")
    new_alerts = []
    from fetchers.gas_monitor import check_gas_health
    async for alert in check_gas_health():
        new_alerts.append(alert)
    if new_alerts:
        print(f"[GAS_MONITOR] 📤 Sending {len(new_alerts)} alerts...")
        await send_notifications(new_alerts)
        print(f"[GAS_MONITOR] ✅ Sent {len(new_alerts)} new alerts.")
    else:
        print("[GAS_MONITOR]  No new data.")

def setup_scheduler():
    configs = settings.load_example_configs()
    for name, cfg in configs.items():
        scheduler.add_job(run_task, "interval", args=[name, cfg], minutes=settings.check_interval_minutes, id=name, replace_existing=True, max_instances=1)
    
    try:
        solana_config = settings.load_config("solana_watch")
        if solana_config:
            scheduler.add_job(run_task, "interval", args=["solana_watch", solana_config], 
                             minutes=solana_config.get("check_interval_minutes", 10), 
                             id="solana_watch", replace_existing=True, max_instances=1)
            print("⏱️ Solana monitor loaded.")
    except Exception as e:
        print(f"⚠️ Could not load Solana monitor: {e}")
        
    scheduler.add_job(check_and_execute_exits, "interval", minutes=5, id="exit_manager", replace_existing=True, max_instances=1)
    print("⏱️ Exit Manager loaded (checking positions every 5 mins).")

    scheduler.add_job(run_task, "interval", args=["githubwatch", {"type": "github"}], minutes=15, id="githubwatch", replace_existing=True, max_instances=1)
    print("⏱️ GitHub Code-First Scanner loaded (checking repos every 15 mins).")
    
    scheduler.add_job(run_insider_watch, "interval", minutes=10, id="insider_watch", replace_existing=True, max_instances=1)
    print("⏱️ Insider Tracker loaded (scanning wallets every 10 mins).")
    
    # 🚨 NEW: Phase 10 Gas Monitor 🚨
    scheduler.add_job(run_gas_check, "interval", minutes=30, id="gas_monitor", replace_existing=True, max_instances=1)
    print("⏱️ Gas Monitor loaded (checking balance every 30 mins).")
    
    print(f"⏱️ Scheduler loaded with {len(configs) + 4} tasks.")
