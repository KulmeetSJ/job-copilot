"""CLI entrypoint for the Local Interactive Browser Agent."""

import argparse
import asyncio
import os
import platform
import socket
import sys
from typing import List, Optional

from job_copilot.browser_agent.agent_runner import LocalBrowserAgentRunner
from job_copilot.browser_agent.client import AgentProtocolClient
from job_copilot.browser_agent.config import (
    AgentConfig,
    clear_agent_config,
    load_agent_config,
    save_agent_config,
)


def get_default_device_name() -> str:
    """Generate a friendly default device name based on local hostname."""
    try:
        host = socket.gethostname()
        system = platform.system()
        return f"{system} ({host})"
    except Exception:
        return "Local Interactive Machine"


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="job-copilot-agent",
        description="Job Copilot Local Interactive Browser Agent CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Agent command to run")

    # pair
    pair_parser = subparsers.add_parser("pair", help="Pair this machine with your Job Copilot dashboard")
    pair_parser.add_argument("code", help="6-digit pairing code shown in the dashboard")
    pair_parser.add_argument("--server", "-s", default="http://localhost:8000", help="Job Copilot server URL")
    pair_parser.add_argument("--name", "-n", default=get_default_device_name(), help="Friendly name for this machine")

    # start
    start_parser = subparsers.add_parser("start", help="Start the local browser agent execution loop")
    start_parser.add_argument("--headless", action="store_true", help="Run in headless mode (disables visible browser interaction)")
    start_parser.add_argument("--poll-interval", type=float, default=3.0, help="Task polling interval in seconds")

    # status
    subparsers.add_parser("status", help="Check device pairing and connectivity status")

    # revoke / reset
    subparsers.add_parser("reset", help="Clear local device credentials and reset configuration")

    return parser.parse_args(args)


async def main_async(args: argparse.Namespace) -> int:
    config = load_agent_config()

    if args.command == "pair":
        print(f"[*] Pairing with Job Copilot at {args.server} using code '{args.code}'...")
        config.server_url = args.server
        config.device_name = args.name
        client = AgentProtocolClient(config)
        try:
            res = await client.pair(pairing_code=args.code, server_url=args.server, device_name=args.name)
            save_agent_config(config)
            print("\n" + "=" * 50)
            print(f"  [SUCCESS] Device Paired Successfully!")
            print(f"  Device ID:   {res['device_id']}")
            print(f"  Device Name: {res['device_name']}")
            print(f"  Server URL:  {res['server_url']}")
            print("=" * 50)
            print("\nYou can now start the agent using:\n  python -m job_copilot.browser_agent start\n")
            return 0
        except Exception as e:
            print(f"[ERROR] Pairing failed: {e}")
            return 1

    elif args.command == "status":
        if not config.device_token:
            print("[INFO] No paired device token found. Run `pair` to connect.")
            return 1
        print(f"[*] Checking device status at {config.server_url}...")
        client = AgentProtocolClient(config)
        try:
            info = await client.get_device_info()
            print("\n" + "=" * 50)
            print(f"  Device ID:    {info.get('device_id')}")
            print(f"  Device Name:  {info.get('device_name')}")
            print(f"  Status:       {info.get('status')}")
            print(f"  Capabilities: {', '.join(info.get('capabilities', []))}")
            print(f"  Last Seen:    {info.get('last_seen_at')}")
            print("=" * 50 + "\n")
            return 0
        except Exception as e:
            print(f"[ERROR] Status check failed: {e}")
            return 1

    elif args.command == "reset":
        clear_agent_config()
        print("[SUCCESS] Local device credentials and configuration cleared.")
        return 0

    elif args.command == "start" or args.command is None:
        if not config.device_token:
            print("[ERROR] Machine is not paired yet.")
            print("Please open the dashboard, generate a pairing code, and run:")
            print("  python -m job_copilot.browser_agent pair <CODE>\n")
            return 1

        if hasattr(args, "headless") and args.headless:
            config.headless = True
        if hasattr(args, "poll_interval") and args.poll_interval:
            config.poll_interval_seconds = args.poll_interval

        runner = LocalBrowserAgentRunner(config)
        try:
            await runner.start()
        except KeyboardInterrupt:
            await runner.shutdown()
        return 0

    return 0


def main(args: Optional[List[str]] = None) -> None:
    parsed = parse_args(args)
    sys.exit(asyncio.run(main_async(parsed)))


if __name__ == "__main__":
    main()
