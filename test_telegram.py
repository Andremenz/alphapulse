import asyncio
import os
from notifiers.platform_notifier import send_notifications

async def main():
    print("🧪 Testing Telegram delivery...")
    
    # Hardcoded test alert
    test_alert = [{
        "type": "whale_buy",
        "value_eth": 25.5,
        "to": "0xTestAddress123456789",
        "tx_hash": "0xTestTxHash123456789abcdef"
    }]
    
    try:
        await send_notifications(test_alert)
        print("✅ SUCCESS: Alert sent to Telegram!")
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
