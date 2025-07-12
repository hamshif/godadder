import sqlite3
import time
import requests
import json
import pandas as pd

import os
import sys

from godadder.util import get_db_full_path, get_godaddy_headers


DB_FILE = get_db_full_path(__file__)



# GODADDY_API_KEY = "3mM44Ywf7decqd_XWuyLNWQbuGZ9ZKWhcdcEd"
# GODADDY_API_SECRET = "CDXZLbQB2ryxs15uHd2kS8"
BASE_URL = "https://api.ote-godaddy.com/v1"
MAX_CALLS_PER_MINUTE = 59



# --- DATABASE ---

def setup_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS domains (
            name TEXT PRIMARY KEY,
            available INTEGER,
            definitive INTEGER,
            price_error TEXT,
            price REAL,
            raw_json TEXT,
            conceived INTEGER
        )""")
        # If column does not exist, add it (for upgrades)
        try:
            c.execute("ALTER TABLE domains ADD COLUMN conceived INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()


def get_existing_domains():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT name FROM domains")
        return set(row[0] for row in c.fetchall())

def upsert_domain(name, info):
    conceived = int(time.time())
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO domains 
            (name, available, definitive, price_error, price, raw_json, conceived)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT conceived FROM domains WHERE name = ?), ?))
        """, (
            name,
            int(info.get('available', False)),
            int(info.get('definitive', False)),
            info.get('price_error', ''),
            info.get('price', None),
            json.dumps(info, ensure_ascii=False),
            name,  # for subquery (keep old value on update)
            conceived  # if new, set to now
        ))
        conn.commit()

# --- GODADDY CHECKS ---

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
            info['available'] = data.get('available', False)
            info['definitive'] = data.get('definitive', False)
        else:
            info['error'] = f"Availability: {resp.status_code} {resp.text}"
            results[domain] = info
            continue

        if info.get('available'):
            wait_if_needed(request_times)
            price_url = f"{BASE_URL}/domains/price/{domain}?action=register"
            price_resp = requests.get(price_url, headers=headers)
            request_times.append(time.time())
            if price_resp.status_code == 200:
                price_data = price_resp.json()
                info['price_micro'] = price_data.get("price", 0)
                info['currency'] = price_data.get("currency", "USD")
                info['price'] = price_data.get("price", 0) / 1_000_000
            elif price_resp.status_code == 404:
                info['price_error'] = "Pricing not available for this TLD in OTE"
            else:
                info['price_error'] = f"Price: {price_resp.status_code} {price_resp.text}"
        results[domain] = info
    return results



def investigate_domains(conf, check_domains):
    setup_db()
    checked = get_existing_domains()
    to_check = [d for d in check_domains if d not in checked]
    print("Domains to check (not yet in db):", to_check)

    results = check_godaddy_domains(to_check, conf)
    for domain, info in results.items():
        upsert_domain(domain, info)
    print(f"Saved {len(results)} new domain results to {DB_FILE}.")
    

def select_domains(columns=None, limit=None, order_by=None, desc=False):
    """
    Selects domains from the DB as a pandas DataFrame.
    """
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        # Get columns for SELECT
        if columns is None:
            c.execute('PRAGMA table_info(domains)')
            columns = [row[1] for row in c.fetchall()]
        col_str = ', '.join(columns)
        sql = f"SELECT {col_str} FROM domains"
        if order_by:
            sql += f" ORDER BY {order_by} {'DESC' if desc else ''}"
        if limit:
            sql += f" LIMIT {limit}"
        df = pd.read_sql_query(sql, conn)
        # Convert UNIX timestamp to datetime (if present)
        if "conceived" in df.columns:
            df["conceived"] = pd.to_datetime(df["conceived"], unit="s", errors='coerce')
        return df


