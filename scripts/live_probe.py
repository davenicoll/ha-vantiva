"""Read-only live check of the client library against a real gateway.

Reads VANTIVA_HOST, VANTIVA_USERNAME and VANTIVA_PASSWORD from the environment, logs in once,
fetches the same pages the integration polls (plus the fallback client table for comparison),
prints a redacted summary and logs out. Only GET requests plus the SRP login/logout POSTs are
made. Never run in CI.

    docker run --rm -v "$PWD":/app -w /app --env-file .env python:3.14-slim \
        sh -c "pip install -q aiohttp && python scripts/live_probe.py"
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from custom_components.vantiva.vantiva_client import (
    VantivaClient,
    VantivaError,
    VantivaLockedOutError,
)
from custom_components.vantiva.vantiva_client.client import PAGE_DEVICES_TABLE
from custom_components.vantiva.vantiva_client.parsers import (
    parse_lan_clients_table,
)


def mask_mac(mac: str) -> str:
    return f"{mac[:2]}:xx:xx:xx:xx:{mac[-2:]}"


def present(value: object) -> str:
    return "present" if value else "missing"


async def main() -> int:
    try:
        host = os.environ["VANTIVA_HOST"]
        username = os.environ["VANTIVA_USERNAME"]
        password = os.environ["VANTIVA_PASSWORD"]
    except KeyError as err:
        print(f"Missing environment variable {err.args[0]}")
        return 2

    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar) as session:
        client = VantivaClient(host, username, password, session)
        try:
            await client.async_login()
        except VantivaLockedOutError as err:
            print(f"Locked out: wait {err.wait_seconds} s (failed attempts {err.wrong_count})")
            return 1
        except VantivaError as err:
            print(f"Login failed: {type(err).__name__}: {err}")
            return 1
        try:
            data = await client.async_get_data()
            table_html = await client._async_fetch_page(PAGE_DEVICES_TABLE, allow_missing=True)
            table = parse_lan_clients_table(table_html) if table_html else {}
        except VantivaError as err:
            print(f"Fetch failed: {type(err).__name__}: {err}")
            return 1
        finally:
            await client.async_logout()
        logged_out = not client.is_authenticated

    gw, wan, gpon = data.gateway, data.wan, data.gpon
    print("== Gateway ==")
    print(f"vendor/product   : {gw.vendor} {gw.product} (hw {gw.hardware_version})")
    print(f"software         : {gw.software_version}")
    print(f"firmware         : {gw.firmware_version}")
    print(f"serial / mac     : {present(gw.serial)} / {present(gw.mac)}")
    print(f"uptime           : {gw.uptime}")
    print(f"memory / cpu     : {gw.memory_pct} % / {gw.cpu_pct} %")
    print(f"reboot cause     : {gw.reboot_cause}")
    print("== WAN ==")
    print(f"connected        : {wan.connected}")
    print(f"link up / gpon up: {wan.link_up} / {wan.gpon_up}")
    print(f"ipv4 / ipv6 / gw : {present(wan.ipv4)} / {present(wan.ipv6)} / {present(wan.gateway)}")
    print(f"dns servers      : {len(wan.dns)}")
    print(f"lease obtained   : {present(wan.lease_obtained)}, expires {present(wan.lease_expires)}")
    print(f"rx / tx bytes    : {wan.rx_bytes} / {wan.tx_bytes}")
    print(f"rx / tx packets  : {wan.rx_packets} / {wan.tx_packets}")
    print(f"rx / tx errors   : {wan.rx_errors} / {wan.tx_errors}")
    print("== GPON ==")
    if gpon is None:
        print("not available")
    else:
        print(f"bandwidth up/down: {gpon.bandwidth_up_mbps}/{gpon.bandwidth_down_mbps} Mbps")
        print(f"wavelength up/dn : {gpon.wavelength_up_nm}/{gpon.wavelength_down_nm} nm")
        print(f"transceiver      : {gpon.transceiver_type}")
        print(f"tx / rx power    : {gpon.tx_power_dbm} / {gpon.rx_power_dbm} dBm")
        print(f"bias / vcc / temp: {gpon.bias_ma} mA / {gpon.vcc_v} V / {gpon.temperature_c} C")
    print("== Clients ==")
    clients = data.clients
    print(f"device-modal     : {len(clients)} clients, {data.active_client_count} active")
    print(f"connection types : {dict(Counter(c.connection.value for c in clients.values()))}")
    print(
        f"with ip / ipv6   : {sum(bool(c.ip) for c in clients.values())} / "
        f"{sum(bool(c.ipv6) for c in clients.values())}"
    )
    print(f"ipv6devices table: {len(table)} rows, {sum(c.active for c in table.values())} active")
    only_json = len(set(clients) - set(table))
    only_table = len(set(table) - set(clients))
    mismatched = sum(
        1 for mac in set(clients) & set(table) if clients[mac].active != table[mac].active
    )
    print(f"json-only / table-only / state mismatch: {only_json} / {only_table} / {mismatched}")
    for lan in list(clients.values())[:3]:
        print(
            f"  {lan.hostname!s:<24} {mask_mac(lan.mac)} active={lan.active} "
            f"{lan.connection.value} port={lan.port} speed={lan.speed_mbps}"
        )
    print(f"logged out       : {logged_out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
