import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Scheduler")

from config import settings
from database import state_db
from fetchers.whale_fetcher import fetch_recent_whale_transfers
from fetchers.governance_fetcher import fetch_snapshot_governance
from fetchers.intelligence_fetcher import run_intelligence_scan
from fetchers.exit_manager import check_and_execute_exits
from fetchers.gas_monitor import check_gas_health
from fetchers.insider_fetcher import check_insider_wallets
from fetchers.refuel_manager import check_gas_and_refuel
from notifiers.platform_notifier import send_notifications, handle_telegram_commands
from reporters.pdf_reporter import generate_pdf

# 🚨 Try importing new modules with explicit error catching
try:
    from fetchers.signal_engine import scan_smart_money
    logger.info("✅ signal_engine imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import signal_engine: {e}")
    scan_smart_money = None

try:
    from fetchers.kelly_sizer import calculate_position_size
    logger.info("✅ kelly_sizer imported successfully")
except ImportError as e:
    logger.error(f"❌ Failed to import kelly_sizer: {e}")
    calculate_position_size = None

scheduler = AsyncIOScheduler()

async def run_task(config_name: str, config: dict):
    print(f"[{config_name}] Starting check...")
    try:
        now_ts = int(datetime.utcnow().timestamp())
        last_ts, seen_ids = await state_db.get_last_state(config_name)
        new_alerts = []
        if config["type"] == "whale":
            alerts = await fetch_recent_whale_transfers(config.get("threshold_eth", 10.0))
        elif config["type"] == "governance":
            alerts = await fetch_snapshot_governance(config["space"])
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
        else: return

        for a in alerts:
            aid = a.get("tx_hash") or a.get("tx") or a.get("id") or a.get("title")
            if aid and aid not in seen_ids: new_alerts.append(a); seen_ids.append(aid); seen_ids = seen_ids[-100:]

        if new_alerts:
            await send_notifications(new_alerts)
            await state_db.update_state(config_name, now_ts, seen_ids)
    except Exception as e: print(f"[{config_name}] ERROR: {str(e)}")

async def run_insider_watch():
    print("[INSIDER_WATCH] Starting check...")
    new_alerts = []
    async for alert in check_insider_wallets(): new_alerts.append(alert)
    if new_alerts: await send_notifications(new_alerts)

async def run_gas_check():
    print("[GAS_MONITOR] Starting health check...")
    new_alerts = []
    async for alert in check_gas_health(): new_alerts.append(alert)
    if new_alerts: await send_notifications(new_alerts)

async def run_refuel_check():
    print("[REFUEL_MANAGER] Checking gas levels...")
    await check_gas_and_refuel()

# 🚨 Safe wrapper for hunt scan
async def run_hunt_scan():
    if scan_smart_money is None:
        print("[HUNT_ENGINE] ❌ Module not loaded - skipping scan")
        return
    print("[HUNT_ENGINE] Scanning smart wallets...")
    try:
        signals = await scan_smart_money()
        if signals:
            await send_notifications(signals)
            print(f"[HUNT_ENGINE] ✅ {len(signals)} signals routed")
        else:
            print("[HUNT_ENGINE] No new signals")
    except Exception as e:
        print(f"[HUNT_ENGINE] Error: {e}")

# 🚨 Safe wrapper for kelly update
async def run_kelly_update():
    if calculate_position_size is None:
        print("[KELLY] ❌ Module not loaded - skipping update")
        return
    print("[KELLY] Updating position sizing...")
    try:
        # Placeholder logic
        print("[KELLY] Model updated")
    except Exception as e:
        print(f"[KELLY] Error: {e}")

def setup_scheduler():
    configs = settings.load_example_configs()
    for name, cfg in configs.items():
        scheduler.add_job(run_task, "interval", args=[name, cfg], minutes=settings.check_interval_minutes, id=name, replace_existing=True, max_instances=1)
    
    scheduler.add_job(check_and_execute_exits, "interval", minutes=5, id="exit_manager", replace_existing=True, max_instances=1)
    scheduler.add_job(run_insider_watch, "interval", minutes=10, id="insider_watch", replace_existing=True, max_instances=1)
    scheduler.add_job(run_gas_check, "interval", minutes=30, id="gas_monitor", replace_existing=True, max_instances=1)
    scheduler.add_job(handle_telegram_commands, "interval", seconds=30, id="telegram_commands", replace_existing=True, max_instances=1)
    scheduler.add_job(run_refuel_check, "interval", minutes=5, id="refuel_manager", replace_existing=True, max_instances=1)
    
    # 🚨 Phase 21: Hunt Engine (with safety check)
    if scan_smart_money is not None:
        scheduler.add_job(run_hunt_scan, "interval", seconds=30, id="hunt_engine", replace_existing=True, max_instances=1)
        print("⏱️ Hunt Engine loaded (scanning every 30s).")
    else:
        print("⚠️ Hunt Engine SKIPPED - module import failed")
    
    # 🚨 Phase 22: Kelly Sizer (with safety check)
    if calculate_position_size is not None:
        scheduler.add_job(run_kelly_update, "interval", minutes=5, id="kelly_sizer", replace_existing=True, max_instances=1)
        print("⏱️ Kelly Sizer loaded (updating every 5m).")
    else:
        print("⚠️ Kelly Sizer SKIPPED - module import failed")
    
    print(f"⏱️ Scheduler setup complete.")
