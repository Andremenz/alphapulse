import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings
from database import state_db
from fetchers.whale_fetcher import fetch_recent_whale_transfers
from fetchers.governance_fetcher import fetch_snapshot_governance
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
        elif config["type"] == "digest":
            alerts = [{"type": "weekly_digest", "total_events": len(seen_ids), "top_space": config.get("space", "N/A"), "period": "7d"}]
        else:
            return

        for a in alerts:
            aid = a.get("tx_hash") or a.get("id") or a.get("title")
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
            print(f"[{config_name}] ⏳ No new data.")
            
    except Exception as e:
        print(f"[{config_name}] ❌ ERROR: {str(e)}")
        import traceback
        print(traceback.format_exc())

def setup_scheduler():
    configs = settings.load_example_configs()
    for name, cfg in configs.items():
        scheduler.add_job(
            run_task, "interval",
            args=[name, cfg],
            minutes=settings.check_interval_minutes,
            id=name,
            replace_existing=True,
            max_instances=1
        )
    print(f"⏱️ Scheduler loaded with {len(configs)} tasks.")
