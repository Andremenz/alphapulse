import os
import json
import time
from web3 import Web3
from fetchers.chain_config import get_chain

CFG = get_chain()
W3 = CFG["w3"]
CHAIN_ID = CFG["chain_id"]

# Aerodrome V2 Router on Base (Dominant Liquidity Hub)
AERODROME_ROUTER_ADDRESS = Web3.to_checksum_address("0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43")
# Aerodrome V2 Factory on Base
AERODROME_FACTORY_ADDRESS = Web3.to_checksum_address("0x420DD381b31aEf6683db6B902084cB0FFECe40Da")
WETH_ADDRESS = Web3.to_checksum_address(CFG["weth_address"])

# Aerodrome Router ABI (Specific to Solidly Ve(3,3) forks)
# Note the 'Route[]' tuple struct: (from, to, stable, factory)
AERODROME_ROUTER_ABI = json.loads('''[
{
  "inputs": [
    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
    {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
    {
      "components": [
        {"internalType": "address", "name": "from", "type": "address"},
        {"internalType": "address", "name": "to", "type": "address"},
        {"internalType": "bool", "name": "stable", "type": "bool"},
        {"internalType": "address", "name": "factory", "type": "address"}
      ],
      "internalType": "struct IRouter.Route[]",
      "name": "routes",
      "type": "tuple[]"
    },
    {"internalType": "address", "name": "to", "type": "address"},
    {"internalType": "uint256", "name": "deadline", "type": "uint256"}
  ],
  "name": "swapExactTokensForETH",
  "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
  "stateMutability": "nonpayable",
  "type": "function"
},
{
  "inputs": [
    {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
    {
      "components": [
        {"internalType": "address", "name": "from", "type": "address"},
        {"internalType": "address", "name": "to", "type": "address"},
        {"internalType": "bool", "name": "stable", "type": "bool"},
        {"internalType": "address", "name": "factory", "type": "address"}
      ],
      "internalType": "struct IRouter.Route[]",
      "name": "routes",
      "type": "tuple[]"
    }
  ],
  "name": "getAmountsOut",
  "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
  "stateMutability": "view",
  "type": "function"
}
]''')

router_contract = W3.eth.contract(address=AERODROME_ROUTER_ADDRESS, abi=AERODROME_ROUTER_ABI)

def get_onchain_price_and_min_out(token_address: str, amount_in_wei: int, slippage_bps: int = 150):
    """
    Fetches exact on-chain output amount from Aerodrome.
    slippage_bps: 150 = 1.5% slippage tolerance (Protects against MEV sandwiches).
    Returns (expected_out_wei, min_out_wei)
    """
    token_addr_cs = Web3.to_checksum_address(token_address)
    # Aerodrome Route struct: from, to, stable, factory
    # Most low-cap Base tokens are paired with WETH in Volatile pools (stable=False)
    routes = [
        (token_addr_cs, WETH_ADDRESS, False, AERODROME_FACTORY_ADDRESS)
    ]
    try:
        amounts = router_contract.functions.getAmountsOut(amount_in_wei, routes).call()
        expected_out_wei = amounts[-1]
        # Calculate min_out with strict slippage tolerance
        min_out_wei = int(expected_out_wei * (10000 - slippage_bps) / 10000)
        return expected_out_wei, min_out_wei
    except Exception as e:
        print(f"[AERODROME] ⚠️ getAmountsOut failed (Liquidity too low or pool mismatch): {e}")
        return 0, 0

def execute_aerodrome_swap(private_key: str, token_address: str, amount_in_wei: int, min_out_wei: int):
    account = W3.eth.account.from_key(private_key)
    wallet_address = account.address
    token_addr_cs = Web3.to_checksum_address(token_address)
    routes = [
        (token_addr_cs, WETH_ADDRESS, False, AERODROME_FACTORY_ADDRESS)
    ]
    deadline = int(time.time()) + 600  # 10 minutes
    try:
        swap_txn = router_contract.functions.swapExactTokensForETH(
            amount_in_wei,
            min_out_wei,
            routes,
            wallet_address,
            deadline
        ).build_transaction({
            'from': wallet_address,
            'gas': 450000,  # Aerodrome swaps can be gas-heavy
            'gasPrice': int(W3.eth.gas_price * 1.1),  # 10% gas bump for priority inclusion
            'nonce': W3.eth.get_transaction_count(wallet_address),
            'chainId': CHAIN_ID
        })
        signed_swap = W3.eth.account.sign_transaction(swap_txn, private_key)
        swap_hash = W3.eth.send_raw_transaction(signed_swap.rawTransaction)
        return W3.to_hex(swap_hash)
    except Exception as e:
        print(f"[AERODROME] ❌ Swap execution failed: {e}")
        return None
