#!/usr/bin/env python3
import sys
import os
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

import colorama
from colorama import Fore, Style

from backend import WalletChecker

BANNER = f"""{Fore.GREEN}{Style.BRIGHT}
⠀⠀⠀⠀⠀⠀⠀⢀⣀⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⡤⡄⠒⠊⠉⢀⣀⢨⠷⡄⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢀⡇⠈⢹⣩⢟⣜⣐⡵⡿⢇⠀⠀⠀⠀⠀⠀
⠀⠀⡠⠖⠊⠉⠀⠀⠈⠻⢅⠀⠀⠀⠀⠀⠈⠒⠠⢀⠀⠀
⠀⡜⠁⠀⠀⠀⠀⠀⠀⠀⠀⠙⠢⣄⠀⠀⠀⠀⣀⣀⣼⠂
⢰⠃⠀⠀⠀⡀⡀⠀⠀⠀⠀⠀⠀⠈⢷⡲⡺⣩⡤⢊⠌⡇
⠸⡆⠀⠀⡞⠀⡇⠀⢰⣓⢢⣄⠀⠀⢸⣞⡞⢉⠔⡡⢊⣷
⠀⢣⠀⠀⠹⡄⡇⠀⢸⣂⡡⢖⠳⣄⢸⢋⠔⡡⢊⣰⠠⠋
⠀⠀⢣⡀⠀⠈⠁⠀⠸⣗⠾⣙⣭⡾⢿⡶⢏⠁⠀⠀⠀⠀
⠀⠀⠀⠳⡀⠀⠀⠀⠀⠻⣽⠊⣡⠞⢉⢔⠝⣑⢄⠀⠀⠀
⠀⠀⠀⢀⣹⣆⠀⠀⠀⠀⠈⠳⣤ ⢊⠔⡡⠊⢁⡤⠓⠄⠀
⠀⡶⡿⣋⣵⢟⣧⠀⠀⠀⠀⠀⠈⢧⡊⣀⠔⡩⠐⣀⠙⡄
⠸⡇⢹⣋⠕⡫⠘⡇⠀⣄⠀⠀⠀⠀⢻⡕⢁⠤⠊⢁⡀⡇
⠀⡇⠀⠳⣵⢊⢽⡇⠀⡏⢳⡀⠀⠀⠀⣟⣡⠴⠚⡉⠠⡇
⠀⠘⢆⡀⠈⠉⠉⠀⠀⣧⣼⡗⠀⠀⠀⣹⠐⣈⠠⠤⣰⠀
⠀⠀⠀⠙⠦⡀⠀⠀⠀⠉⠉⠀⠀⠀⢀⡯⠥⣒⣂⡱⠃⠀
⠀⠀⠀⠀⠀⠈⢧⠀⠀⠀⠀⠀⠀⢀⣞⣉⠭⠴⠋⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠘⡆⠀⡶⣶⠶⠒⠉⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠈⠉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
{Fore.RED}{Style.BRIGHT}          BALCHE CLI{Style.RESET_ALL}"""

def load_addresses() -> list[str]:
    prompt = f"{Style.BRIGHT}Path to wallet file (blank to paste):       {Style.RESET_ALL}"
    path = input(prompt).strip()
    if path:
        p = Path(path).expanduser()
        if not p.is_file():
            print(f"{Fore.RED}{Style.BRIGHT}File not found:{Style.RESET_ALL} {p}")
            sys.exit(1)
        addrs = [l.strip() for l in p.read_text().splitlines() if l.strip()]
        print(f"{Fore.GREEN}✔ Loaded {len(addrs)} addresses from {p}{Style.RESET_ALL}")
    else:
        print(f"{Style.BRIGHT}Paste addresses, end with blank line:{Style.RESET_ALL}")
        addrs = []
        while True:
            l = input().strip()
            if not l:
                break
            addrs.append(l)
        print(f"{Fore.GREEN}✔ Collected {len(addrs)} addresses{Style.RESET_ALL}")
    if not addrs:
        print(f"{Fore.RED}{Style.BRIGHT}No addresses provided{Style.RESET_ALL}")
        sys.exit(0)
    return addrs

def colored_status(status: str) -> str:
    return (Fore.GREEN if status.lower().startswith('success') else Fore.RED) + status + Style.RESET_ALL

def print_single(result: Dict):
    addr = result['address']
    typ  = result['type']

    positive = False
    if typ == 'EVM':
        positive = any(v['balance'] > 0 for v in result['balances'].values())
        for chain in result.get('token_balances', {}):
            for tok in result['token_balances'][chain].values():
                if tok['balance'] > 0:
                    positive = True
    elif typ == 'TRX':
        for tok_info in result['balances'].values():
            if tok_info['balance'] > 0:
                positive = True
    elif typ == 'SOL':
        if result.get('balance', 0.0) > 0:
            positive = True
        for tok in result.get('token_balances', {}).get('SOL', {}).values():
            if tok['balance'] > 0:
                positive = True
    else:
        positive = result.get('balance', 0.0) > 0

    indicator = (Fore.GREEN + "[+]" if positive else Fore.RED + "[-]") + Style.RESET_ALL
    print(f"\n{indicator} {Fore.WHITE}{Style.BRIGHT}Address:{Style.RESET_ALL} {Fore.CYAN}{addr}{Style.RESET_ALL}")

    if typ == 'EVM':
        for chain, info in result['balances'].items():
            print(f"  {Fore.MAGENTA}{Style.BRIGHT}{chain}:{Style.RESET_ALL} "
                  f"{Fore.YELLOW}{info['balance']:.8f}{Style.RESET_ALL}   "
                  f"{colored_status(info['status'])}")
        for chain, tokens in result['token_balances'].items():
            for sym, tok in tokens.items():
                print(f"  {Fore.BLUE}{Style.BRIGHT}{chain} ({sym}):{Style.RESET_ALL} "
                      f"{Fore.YELLOW}{tok['balance']:.8f}{Style.RESET_ALL}   "
                      f"{colored_status(tok['status'])}")

    elif typ == 'TRX':
        for sym, info in result['balances'].items():
            print(f"  {Fore.MAGENTA}{Style.BRIGHT}{sym}:{Style.RESET_ALL} "
                  f"{Fore.YELLOW}{info['balance']:.6f}{Style.RESET_ALL}   "
                  f"{colored_status(info['status'])}")

    elif typ == 'SOL':
        bal = result.get('balance', 0.0)
        print(f"  {Fore.MAGENTA}{Style.BRIGHT}SOL:{Style.RESET_ALL} "
              f"{Fore.YELLOW}{bal:.8f}{Style.RESET_ALL}   "
              f"{colored_status(result['status'])}")
        for sym, tok in result.get('token_balances', {}).get('SOL', {}).items():
            print(f"  {Fore.BLUE}{Style.BRIGHT}{sym}:{Style.RESET_ALL} "
                  f"{Fore.YELLOW}{tok['balance']:.8f}{Style.RESET_ALL}   "
                  f"{colored_status(tok['status'])}")

    else:
        bal = result.get('balance', 0.0)
        print(f"  {Fore.MAGENTA}{Style.BRIGHT}{typ}:{Style.RESET_ALL} "
              f"{Fore.YELLOW}{bal:.8f}{Style.RESET_ALL}   "
              f"{colored_status(result['status'])}")

    print(f"{Fore.WHITE}{Style.DIM}{'-'*50}{Style.RESET_ALL}")

def worker(addr: str, checker: WalletChecker) -> Dict:
    try:
        return checker.get_balance(addr)
    except Exception as e:
        return {
            'address': addr,
            'type': checker.detect_wallet_type(addr),
            'balance': 0.0,
            'status': f'error:{e}'
        }

def main():
    colorama.init(autoreset=True)
    print(BANNER)
    addrs = load_addresses()
    checker = WalletChecker()

    results = []
    with ThreadPoolExecutor(max_workers=5) as exe:
        future_to_addr = {exe.submit(worker, addr, checker): addr for addr in addrs}
        for fut in as_completed(future_to_addr):
            res = fut.result()
            results.append(res)
            print_single(res)

    if input(f"{Style.BRIGHT}Save to ~/wallet_balances.json? [y/N]: {Style.RESET_ALL}").strip().lower() == 'y':
        out = Path.home() / "wallet_balances.json"
        out.write_text(json.dumps(results, indent=2))
        print(f"{Fore.GREEN}{Style.BRIGHT}Results saved to {out}{Style.RESET_ALL}")

if __name__ == "__main__": main()
