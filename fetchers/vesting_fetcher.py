async def fetch_vesting_releases(contract_address: str, chain: str = "base") -> list:
    """Fetch recent vesting release events from contract."""
    # 🔧 TEST MODE: Return a mock alert to prove the pipeline works
    # Remove this test code once you add real vesting contracts
    return [{
        "type": "vesting_release",
        "contract_name": "TEST-CONTRACT",
        "amount_eth": 1.2345,
        "beneficiary": "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE",
        "tx_hash": "0xTEST123456789abcdef",
        "chain": chain
    }]
