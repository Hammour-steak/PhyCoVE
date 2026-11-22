"""Reserve resource-pack units before submission and wait for sufficient balance safely."""
from decimal import Decimal
import os
from pathlib import Path
import threading
import time

import requests

from kling4_client import atomic_json


class CreditGuard:
    def __init__(self, api_base, state_path=None, existing_holds=None, reader=None, poll_interval=30):
        self.condition = threading.Condition()
        self.state_path = Path(state_path) if state_path else None
        self.poll_interval = poll_interval
        self.next_refresh = 0
        self.session = None
        if reader is None:
            if api_base not in ('https://api-beijing.klingai.com', 'https://api-singapore.klingai.com'):
                raise ValueError('Use an official Kling API base')
            key = os.environ.get('KLING_API_KEY')
            if not key:
                raise RuntimeError('KLING_API_KEY is not set')
            self.session = requests.Session()
            self.session.headers.update({'Authorization': 'Bearer ' + key})

            def reader():
                now = int(time.time() * 1000)
                response = self.session.get(api_base + '/account/costs',
                    params={'start_time': now - 30 * 86400000, 'end_time': now},
                    timeout=30, allow_redirects=False)
                response.raise_for_status()
                body = response.json()
                if body.get('code') != 0:
                    raise RuntimeError('Account credit query failed: ' + str(body))
                return body['data']['resource_pack_subscribe_infos']

        self.reader = reader
        self.tokens = {key: Decimal(str(value)) for key, value in (existing_holds or {}).items()}
        self.available = Decimal(0)
        self.known_totals = {}
        self.initial_available = Decimal(0)
        self.funding_added = Decimal(0)
        self.waiting = False
        self.backend_ready_at = 0
        self.backend_rejections = 0
        self._refresh(initial=True)

    @staticmethod
    def pack_key(pack):
        # Some subscriptions share a resource_pack_id; purchase timestamps distinguish them.
        return tuple(str(pack.get(key, '')) for key in
                     ('resource_pack_id', 'purchase_time', 'effective_time', 'invalid_time'))

    def _refresh(self, initial=False):
        packs = [pack for pack in self.reader() if pack.get('resource_pack_tier') == 'flagship']
        live = sum((Decimal(str(pack['remaining_quantity'])) for pack in packs
                    if pack.get('status') == 'online'), Decimal(0))
        funding = Decimal(0)
        for pack in packs:
            key = self.pack_key(pack)
            total = Decimal(str(pack['total_quantity']))
            if not initial and pack.get('status') == 'online':
                funding += max(Decimal(0), total - self.known_totals.get(key, Decimal(0)))
            self.known_totals[key] = total
        if initial:
            self.initial_available = live
            self.available = max(Decimal(0), live - sum(self.tokens.values(), Decimal(0)))
        else:
            # Never restore spent units from a stale balance snapshot; only an account recharge can increase available credit.
            self.available = max(Decimal(0), min(self.available + funding, live))
            self.funding_added += funding
        self.live_remaining = live
        self.next_refresh = time.monotonic() + self.poll_interval
        self._write()

    def _write(self):
        if self.state_path:
            atomic_json(self.state_path, {
                'available_for_new_submissions': str(self.available),
                'initial_available': str(self.initial_available),
                'new_funding_detected': str(self.funding_added),
                'latest_resource_pack_balance': str(self.live_remaining),
                'reserved_tasks': {key: str(value) for key, value in self.tokens.items()},
                'waiting_for_credit': self.waiting,
                'backend_credit_rejections': self.backend_rejections,
                'backend_cooldown_seconds': max(0, round(self.backend_ready_at - time.monotonic(), 1)),
                'updated_at': time.time()})

    def reserve(self, case_id, amount, stop_new):
        amount = Decimal(str(amount))
        with self.condition:
            if case_id in self.tokens:
                return
            while True:
                if stop_new.is_set():
                    raise RuntimeError('New submissions paused after an unresolved provider task')
                cooldown = self.backend_ready_at - time.monotonic()
                if cooldown > 0:
                    self.condition.wait(timeout=min(5, cooldown))
                    continue
                if self.available >= amount:
                    self.available -= amount
                    self.tokens[case_id] = amount
                    self.waiting = False
                    self._write()
                    return
                if not self.waiting:
                    self.waiting = True
                    self._write()
                    print(f'[credit wait] available={self.available}, next_task={amount}; waiting for sufficient account balance', flush=True)
                if time.monotonic() >= self.next_refresh:
                    try:
                        self._refresh()
                    except Exception as exc:
                        print(f'[credit query retry] {type(exc).__name__}: {exc}', flush=True)
                        self.next_refresh = time.monotonic() + self.poll_interval
                    continue
                self.condition.wait(timeout=max(0.01, min(5, self.next_refresh - time.monotonic())))

    def backend_not_ready(self, seconds=60):
        """Resource-pack visibility can precede availability at the generation service."""
        with self.condition:
            self.backend_ready_at = max(self.backend_ready_at, time.monotonic() + seconds)
            self.backend_rejections += 1
            self._write()
            self.condition.notify_all()
            print(f'[credit backend wait] generation endpoint returned 1102; waiting {seconds}s', flush=True)

    def finish(self, case_id, consumed):
        """Refund only an explicit zero/partial charge; unknown outcomes retain their reservation."""
        with self.condition:
            reserved = self.tokens.pop(case_id, None)
            if reserved is None:
                return
            consumed = reserved if consumed is None else Decimal(str(consumed))
            self.available += reserved - consumed
            self._write()
            self.condition.notify_all()

    def close(self):
        if self.session:
            self.session.close()
