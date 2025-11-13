#!/usr/bin/env python3
import os
import time
import threading
from typing import Dict, List, Any

import requests
import base58
from web3 import Web3
from dotenv import load_dotenv

load_dotenv()

class WalletChecker:
    evm_chains: Dict[str, List[str]] = {
        "ETH": [
            "https://eth.llamarpc.com",
            "https://ethereum.publicnode.com",
        ],
        "BNB": [
            "https://bsc-dataseed.binance.org/",
            "https://bsc-dataseed1.defibit.io/",
            "https://bsc-dataseed1.ninicoin.io/",
            "https://bsc-dataseed2.defibit.io/",
        ],
        "POLYGON": ["https://polygon-rpc.com"],
        "AVAX": ["https://api.avax.network/ext/bc/C/rpc"],
        "ARBITRUM": ["https://arb1.arbitrum.io/rpc"],
        "OPTIMISM": ["https://mainnet.optimism.io"],
        "BASE": ["https://mainnet.base.org"],
        "FANTOM": ["https://rpcapi.fantom.network"],
        "CRONOS": ["https://evm.cronos.org"],
        "HARMONY": ["https://api.harmony.one"],
    }

    SOLANA_RPC = "https://api.mainnet-beta.solana.com"
    SOL_USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL_USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

    erc20_abi = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]

    token_map: Dict[str, Dict[str, Dict[str, Any]]] = {
        "BNB": {
            "XRP": {"address": "0x1d2f0da169ceb9fc7b3144628db156f3f6c60dbe", "decimals": 18},
            "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
            "USDC": {"address": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", "decimals": 18},
        },
        "ETH": {
            "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
            "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
        },
        "POLYGON": {
            "USDC": {"address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "decimals": 6},
        }
    }

    TRONGRID_API = "https://api.trongrid.io"
    USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

    def __init__(self):
        self.evm_clients: Dict[str, List[Web3]] = {
            chain: [Web3(Web3.HTTPProvider(ep)) for ep in endpoints]
            for chain, endpoints in self.evm_chains.items()
        }
        self.current_client_idx: Dict[str, int] = {chain: 0 for chain in self.evm_chains}

        self.last_request_time = 0.0
        self.min_request_interval = 0.3
        self._rate_lock = threading.Lock()

    def _wait_for_rate_limit(self) -> None:
        with self._rate_lock:
            now = time.time()
            delta = now - self.last_request_time
            if delta < self.min_request_interval:
                time.sleep(self.min_request_interval - delta)
            self.last_request_time = time.time()

    def _rotate_client(self, chain: str) -> Web3:
        idx = (self.current_client_idx[chain] + 1) % len(self.evm_clients[chain])
        self.current_client_idx[chain] = idx
        return self.evm_clients[chain][idx]

    def _get_token_balance(self, client: Web3, wallet: str, token_addr: str, decimals: int) -> float:
        contract = client.eth.contract(address=Web3.to_checksum_address(token_addr), abi=self.erc20_abi)
        raw = contract.functions.balanceOf(Web3.to_checksum_address(wallet)).call()
        return raw / (10**decimals)

    def detect_wallet_type(self, address: str) -> str:
        a = address.strip()
        if a.startswith("0x") and len(a) == 42:
            try:
                Web3.to_checksum_address(a)
                return "EVM"
            except Exception:
                pass
        if a.startswith("T") and len(a) == 34:
            return "TRX"
        if 32 <= len(a) <= 44:
            return "SOL"
        return "UNKNOWN"

    def get_evm_balance(self, address: str) -> Dict[str, Any]:
        results: Dict[str, Any] = {"address": address, "type": "EVM", "balances": {}, "token_balances": {}, "status": "success"}

        for chain in self.evm_clients:
            bal = 0.0
            stat = "error"
            for _ in range(len(self.evm_clients[chain])):
                try:
                    self._wait_for_rate_limit()
                    client = self._rotate_client(chain)
                    raw = client.eth.get_balance(Web3.to_checksum_address(address))
                    bal = raw / 1e18
                    stat = "success"
                    break
                except Exception as e:
                    msg = str(e).lower()
                    if "rate limit" in msg or "429" in msg:
                        continue
                    stat = f"error: {e}"
                    break
            results["balances"][chain] = {"balance": bal, "status": stat}
            if stat != "success":
                results["status"] = "partial"

        for chain, tokens in self.token_map.items():
            token_out: Dict[str, Any] = {}
            for sym, meta in tokens.items():
                try:
                    self._wait_for_rate_limit()
                    client = self._rotate_client(chain)
                    tbal = self._get_token_balance(client, address, meta["address"], meta["decimals"])
                    token_out[sym] = {"balance": tbal, "status": "success"}
                except Exception as e:
                    token_out[sym] = {"balance": 0.0, "status": f"error: {e}"}
                    results["status"] = "partial"
            results["token_balances"][chain] = token_out

        return results

    def get_trx_balance(self, address: str) -> Dict[str, Any]:
        out = {"address": address, "type": "TRX", "balances": {}, "status": "success"}

        try:
            self._wait_for_rate_limit()
            url = f"{self.TRONGRID_API}/v1/accounts/{address}"
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
            sun = int(data[0].get("balance", 0)) if data else 0
            out["balances"]["TRX"] = {"balance": sun / 1e6, "status": "success" if data else "error: not found"}
            if not data:
                out["status"] = "partial"
        except Exception:
            out["balances"]["TRX"] = {"balance": 0.0, "status": "error: invalid"}
            out["status"] = "partial"

        try:
            self._wait_for_rate_limit()
            full_hex = base58.b58decode_check(address).hex()
            raw_hex = full_hex[2:]
            param = raw_hex.rjust(64, "0")

            payload = {
                "owner_address":     address,
                "contract_address":  self.USDT_CONTRACT,
                "function_selector": "balanceOf(address)",
                "parameter":         param,
                "visible":           True,
            }
            r2 = requests.post(f"{self.TRONGRID_API}/wallet/triggerconstantcontract", json=payload, timeout=10)
            r2.raise_for_status()
            cr = r2.json().get("constant_result", [])
            if not cr:
                raise ValueError("missing constant_result")
            usdt_int = int(cr[0], 16)
            out["balances"]["USDT"] = {"balance": usdt_int / 1e6, "status": "success"}
        except Exception as e:
            out["balances"]["USDT"] = {"balance": 0.0, "status": f"error: {e}"}
            out["status"] = "partial"

        return out

    def _get_spl_token_balance(self, owner: str, mint: str) -> float:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [
                owner,
                {"mint": mint},
                {"encoding": "jsonParsed"}
            ]
        }
        self._wait_for_rate_limit()
        r = requests.post(self.SOLANA_RPC, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        r.raise_for_status()
        resp = r.json()
        accounts = resp.get("result", {}).get("value", []) or []
        total = 0.0
        for acc in accounts:
            parsed = acc.get("account", {}).get("data", {}).get("parsed", {})
            info = parsed.get("info", {})
            amt = info.get("tokenAmount", {})
            ui_amount = amt.get("uiAmount")
            if ui_amount is None:
                raw = int(amt.get("amount", 0) or 0)
                decimals = int(amt.get("decimals", 0) or 0)
                ui_amount = raw / (10 ** decimals) if decimals else 0.0
            total += ui_amount or 0.0
        return total

    def get_sol_balance(self, address: str) -> Dict[str, Any]:
        out = {"address": address, "type": "SOL", "balance": 0.0, "status": "success", "token_balances": {}}
        try:
            self._wait_for_rate_limit()
            payload = {"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]}
            resp = requests.post(self.SOLANA_RPC, json=payload, headers={"Content-Type":"application/json"}, timeout=10)
            resp.raise_for_status()
            val = resp.json().get("result", {}).get("value", 0)
            out["balance"] = val / 1e9
        except Exception as e:
            out["status"] = f"error: {e}"

        spl_tokens: Dict[str, Any] = {}
        for sym, mint in (("USDC", self.SOL_USDC_MINT), ("USDT", self.SOL_USDT_MINT)):
            try:
                self._wait_for_rate_limit()
                amt = self._get_spl_token_balance(address, mint)
                spl_tokens[sym] = {"balance": amt, "status": "success" if amt else "zero"}
            except Exception as e:
                spl_tokens[sym] = {"balance": 0.0, "status": f"error: {e}"}
                out["status"] = "partial"

        out["token_balances"]["SOL"] = spl_tokens
        return out

    def get_balance(self, address: str) -> Dict[str, Any]:
        t = self.detect_wallet_type(address)
        if t == "EVM":
            return self.get_evm_balance(address)
        if t == "TRX":
            return self.get_trx_balance(address)
        if t == "SOL":
            return self.get_sol_balance(address)
        return {"address": address, "type": "UNKNOWN", "balance":0.0, "status":"error: unsupported type"}
