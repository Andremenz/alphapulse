from web3 import Web3
from config import settings
import asyncio
import httpx

def get_rpc_url(chain: str) -> str:
    """Get RPC URL for chain."""
    if not settings.alchemy_api_key:
        # Fallback to public RPC if no API key (not recommended for production)
        if chain == "base":
            return "https://mainnet.base.org"
        elif chain == "ethereum":
            return "https://eth.llamarpc.com"
        else:
            return "https://mainnet.base.org"
    if chain == "base":
        return f"https://base-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"
    elif chain == "ethereum":
        return f"https://eth-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"
    else:
        return f"https://{chain}-mainnet.g.alchemy.com/v2/{settings.alchemy_api_key}"

async def fetch_vesting_releases(contract_address: str, chain: str = "base") -> list:
    """Fetch recent vesting release events from contract."""
    alerts = []
    
    try:
        w3 = Web3(Web3.HTTPProvider(get_rpc_url(chain)))
        
        # Standard vesting contract ABI (Release event)
        abi = [{
            "anonymous": False,
            "inputs": [
                {"indexed": True, "name": "beneficiary", "type": "address"},
                {"indexed": False, "name": "amount", "type": "uint256"}
            ],
            "name": "Release",
            "type": "event"
        }]
        
        # Convert to checksum address
checksum_address = w3.to_checksum_address(contract_address)
contract = w3.eth.contract(address=checksum_address, abi=abi)
        
        # Get events from last 100 blocks
        latest_block = w3.eth.block_number
        from_block = max(0, latest_block - 100)
        
        # ✅ FIX: Use snake_case parameter names (from_block, to_block)
        events = contract.events.Release.get_logs(from_block=from_block, to_block=latest_block)
        
        for event in events:
            amount_eth = w3.from_wei(event['args']['amount'], 'ether')
            tx_hash = event['transactionHash'].hex()
            beneficiary = event['args']['beneficiary']
            
            # Only alert if amount > 0.01 ETH (adjust as needed)
            if amount_eth > 0.01:
                alerts.append({
                    "type": "vesting_release",
                    "contract_name": contract_address[:8] + "..." + contract_address[-4:],
                    "amount_eth": float(amount_eth),
                    "beneficiary": beneficiary,
                    "tx_hash": tx_hash,
                    "chain": chain
                })
        
        print(f"[vesting_fetcher] Found {len(alerts)} vesting releases from {contract_address}")
        
    except Exception as e:
        print(f"[vesting_fetcher] Error fetching from {contract_address}: {e}")
    
    return alerts
