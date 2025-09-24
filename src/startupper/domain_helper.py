import time
import requests
from typing import Iterable

from .persistence import DomainStore, SQLiteDomainStore

BASE_URL = "https://api.ote-godaddy.com/v1"
MAX_CALLS_PER_MINUTE = 59


def get_godaddy_headers(conf):
    return {
        "Authorization": f"sso-key {conf.GODADDY_API_KEY}:{conf.GODADDY_API_SECRET}",
        "Accept": "application/json",
    }


_store_singleton: DomainStore | None = None


def get_domain_store() -> DomainStore:
    """Return the process-wide domain store (default: SQLite)."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = SQLiteDomainStore()
        _store_singleton.setup()
    return _store_singleton


def get_existing_domains() -> set[str]:
    return get_domain_store().get_existing_domains()


def upsert_domain(name: str, info: dict) -> None:
    get_domain_store().upsert_domain(name, info)


def wait_if_needed(request_times):
    now = time.time()
    request_times[:] = [t for t in request_times if now - t < 60]
    if len(request_times) >= MAX_CALLS_PER_MINUTE:
        sleep_time = (request_times[0] + 61) - now
        if sleep_time > 0:
            print(f"API limit reached, sleeping for {sleep_time:.1f} seconds")
            time.sleep(sleep_time)
        now = time.time()
        request_times[:] = [t for t in request_times if now - t < 60]


def check_godaddy_domains(domain_list, conf):
    headers = get_godaddy_headers(conf)
    results = {}
    request_times = []
    for domain in domain_list:
        wait_if_needed(request_times)
        url = f"{BASE_URL}/domains/available?domain={domain}&checkType=FAST"
        resp = requests.get(url, headers=headers)
        request_times.append(time.time())
        info = {}
        if resp.status_code == 200:
            data = resp.json()
            info["available"] = data.get("available", False)
            info["definitive"] = data.get("definitive", False)
        else:
            info["error"] = f"Availability: {resp.status_code} {resp.text}"
            results[domain] = info
            continue

        if info.get("available"):
            wait_if_needed(request_times)
            price_url = f"{BASE_URL}/domains/price/{domain}?action=register"
            price_resp = requests.get(price_url, headers=headers)
            request_times.append(time.time())
            if price_resp.status_code == 200:
                price_data = price_resp.json()
                info["price_micro"] = price_data.get("price", 0)
                info["currency"] = price_data.get("currency", "USD")
                info["price"] = price_data.get("price", 0) / 1_000_000
            elif price_resp.status_code == 404:
                info["price_error"] = "Pricing not available for this TLD in OTE"
            else:
                info["price_error"] = f"Price: {price_resp.status_code} {price_resp.text}"
        results[domain] = info
    return results


def investigate_domains(conf, check_domains: Iterable[str]):
    store = get_domain_store()
    checked = store.get_existing_domains()
    to_check = [d for d in check_domains if d not in checked]
    print("Domains to check (not yet in db):", to_check)

    results = check_godaddy_domains(to_check, conf)
    for domain, info in results.items():
        store.upsert_domain(domain, info)
    print(f"Saved {len(results)} new domain results.")


def select_domains(columns=None, limit=None, order_by=None, desc=False):
    return get_domain_store().select_domains(columns=columns, limit=limit, order_by=order_by, desc=desc)
