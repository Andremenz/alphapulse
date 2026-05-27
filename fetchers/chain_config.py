import os
from web3 import Web3

# 🌐 Chain Configuration Registry
# Add new chains here. Switch by changing ACTIVE_CHAIN env var.
CHAINS = {
    "base": {
        "chain_id": 8453,
        "rpc_url": "https://base-mainnet.flashbots.net", # MEV Protected
        "weth": "0x4200000000000000000000000000000000000006",
        "router": "0x4752ba5DBc23f44D87826276BF6Fd6b1C372aD24", # Uniswap V2
        "explorer": "basescan.org",
        "gecko_slug": "base",
        "tokens": {
            "aerodrome": {"address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631", "ticker": "AERO", "coingecko_id": "aerodrome-finance"},
            "baseswap": {"address": "0x78a087d713Be963Bf307B18F2Ff8122EF9A63ae9", "ticker": "BSWAP", "coingecko_id": "baseswap"},
            "brett": {"address": "0x532f27101965dd16442E59d40670FaF5eBB142E4", "ticker": "BRETT", "coingecko_id": "based-brett"},
        }
    },
    # Example: Add Arbitrum later
    # "arbitrum": { "chain_id": 42161, "rpc_url": "...", "explorer": "arbiscan.io", "gecko_slug": "arbitrum-one", "tokens": {...} }
}

ACTIVE_CHAIN_NAME = os.environ.get("ACTIVE_CHAIN", "base")

def get_chain():
    if ACTIVE_CHAIN_NAME not in CHAINS:
        raise ValueError(f"⛓️ Chain '{ACTIVE_CHAIN_NAME}' not configured. Add it to chain_config.py")
    
    cfg = CHAINS[ACTIVE_CHAIN_NAME]
    cfg["w3"] = Web3(Web3.HTTPProvider(cfg["rpc_url"]))
    cfg["router_address"] = Web3.to_checksum_address(cfg["router"])
    cfg["weth_address"] = Web3.to_checksum_address(cfg["weth"])
    for space, data in cfg["tokens"].items():
        data["address"] = Web3.to_checksum_address(data["address"])
    return cfg
