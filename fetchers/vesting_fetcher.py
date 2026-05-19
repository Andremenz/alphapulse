from web3 import Web3
from config import settings
import asyncio
import httpx

def get_rpc_url(chain: str) -> str:
    """Get RPC URL for chain."""
    if not settings.alchemy_api_key:
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
    
    # 🔧 DEMO MODE: Return mock alert if using test address
    # Remove this block when client provides real contract
    if contract_address.lower() in ["0x0000000000000000000000000000000000000001", "0x9d65ff81a3c488d585bbfb0bfe3c7707c7917f54"]:
        return [{
            "type": "vesting_release",
            "contract_name": "DEMO-CONTRACT",
            "amount_eth": 1.2345,
            "beneficiary": "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE",
            "tx_hash": "0xDEMO123456789abcdef",
            "chain": chain
        }]
    
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
        
        # Use snake_case parameter names
        events = contract.events.Release.get_logs(from_block=from_block, to_block=latest_block)
        
        for event in events:
            amount_eth = w3.from_wei(event['args']['amount'], 'ether')
            tx_hash = event['transactionHash'].hex()
            beneficiary = event['args']['beneficiary']
            
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
