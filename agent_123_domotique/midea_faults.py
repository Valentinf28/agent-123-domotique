"""Read-only C3 fault snapshots. Never export config-entry diagnostics or secrets."""
from __future__ import annotations
import math
import re
import threading
import time
from datetime import datetime, timezone


def extract_fault(diagnostic):
    data = diagnostic.get('data') if isinstance(diagnostic, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get('entry'), dict) or data['entry'].get('domain') != 'midea':
        return None
    attrs = data.get('device_attributes')
    if not isinstance(attrs, dict):
        return None
    # C3 basic response carries tank temperature and fault byte together. Refuse
    # the library's initial/default zero before an actual basic report exists.
    tank, code = attrs.get('tank_actual_temperature'), attrs.get('error_code')
    if (type(tank) not in (int, float) or not math.isfinite(tank)
            or type(code) is not int or not 0 <= code <= 255
            or type(attrs.get('zone1_power')) is not bool
            or not isinstance(attrs.get('zone_target_temp'), list)):
        return None
    return code


class MideaFaultMonitor:
    def __init__(self, clock=time.monotonic, interval=20, ttl=90):
        self.clock, self.interval, self.ttl = clock, interval, ttl
        self.lock = threading.Lock()
        self.cache = {}
        self.next_poll = 0
        self.running = False

    def snapshot(self, entity_id):
        result = {'pac_fault_status': 'unknown', 'pac_fault_code_raw': None,
                  'pac_fault_observed_at': None, 'pac_fault_source': None}
        with self.lock:
            value = self.cache.get(entity_id)
            if value and self.clock() - value['monotonic'] <= self.ttl:
                result.update(value['public'])
        return result

    def request_refresh(self, entity_ids, read_registry, read_diagnostic):
        ids = sorted({value for value in entity_ids if isinstance(value, str)
                      and re.fullmatch(r'climate\.[a-z0-9_]+', value)})[:4]
        with self.lock:
            self.cache = {key: value for key, value in self.cache.items() if key in ids}
            if not ids or self.running or self.clock() < self.next_poll:
                return
            self.running = True
            self.next_poll = self.clock() + self.interval
        try:
            threading.Thread(target=self.refresh, args=(ids, read_registry, read_diagnostic),
                             daemon=True, name='midea-fault-read').start()
        except RuntimeError:
            with self.lock:
                self.running = False

    def refresh(self, ids, read_registry, read_diagnostic):
        diagnostics = {}
        started = self.clock()
        try:
            for entity_id in ids:
                if self.clock() - started > 10:
                    break
                try:
                    before = read_registry(entity_id)
                    entry_id = before.get('config_entry_id') if isinstance(before, dict) else None
                    if (before.get('platform') != 'midea' or not isinstance(entry_id, str)
                            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry_id)):
                        raise ValueError('Unmatched registry identity')
                    if entry_id not in diagnostics:
                        diagnostics[entry_id] = read_diagnostic(entry_id)
                    raw = diagnostics[entry_id]
                    # Reconcile identity after the read, including entry replacement.
                    after = read_registry(entity_id)
                    data = raw.get('data', {}) if isinstance(raw, dict) else {}
                    if (after.get('platform') != 'midea' or after.get('config_entry_id') != entry_id
                            or data.get('entry', {}).get('entry_id') != entry_id):
                        raise ValueError('Registry changed')
                    code = extract_fault(raw)
                    if code is None:
                        raise ValueError('No confirmed C3 fault byte')
                    public = {'pac_fault_status': 'reported' if code else 'not_reported',
                              'pac_fault_code_raw': code,
                              'pac_fault_observed_at': datetime.now(timezone.utc).isoformat(),
                              'pac_fault_source': 'midea_c3_diagnostic_v1'}
                    with self.lock:
                        self.cache[entity_id] = {'monotonic': self.clock(), 'public': public}
                except Exception:
                    # Never log exception bodies or cache provider diagnostics.
                    with self.lock:
                        self.cache.pop(entity_id, None)
        finally:
            with self.lock:
                self.running = False
