import asyncio
import sys
from unittest.mock import patch, AsyncMock

async def run_tests():
    print("🧪 Running AlphaPulse dry-run tests...")
    
    # 1. Config loading
    from config import settings
    assert settings.platform in ("telegram", "discord"), "Platform config failed"
    print("✅ 1. Config loader: PASSED")
    
    # 2. Notifier routing (mocked HTTP)
    from notifiers.platform_notifier import send_notifications, format_alert
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await send_notifications([{"type": "whale_buy", "value_eth": 20.5, "to": "0x1234", "tx_hash": "0xabc"}])
        assert mock_post.called, "Notifier failed to trigger HTTP call"
    print("✅ 2. Notifier routing: PASSED")
    
    # 3. Format consistency
    md = format_alert({"type": "governance", "space": "test", "title": "Prop 1", "votes": "1.2M", "id": "0x1", "timestamp": ""})
    assert "**Governance Closed**" in md and "[View Proposal]" in md, "Markdown formatting broken"
    print("✅ 3. Markdown formatter: PASSED")
    
    print("\n🎉 All tests passed. Bot is ready for live API keys.")

if __name__ == "__main__":
    asyncio.run(run_tests())