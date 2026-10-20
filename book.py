#!/usr/bin/env python3
"""Prenotazione automatica corsi Fit Express (Wellness in Cloud).
Credenziali da variabili d'ambiente FITEXPRESS_EMAIL / FITEXPRESS_PASSWORD.
Uso:
  python book.py              # attende la mezzanotte (Europe/Rome) e prenota
  python book.py --dry-run    # login + mostra i corsi trovati, NON prenota
  python book.py --now        # prova subito senza attendere mezzanotte
"""
import os, sys, time, json, argparse, datetime as dt
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo
import requests, yaml

ROME = ZoneInfo("Europe/Rome")
BASE = "https://mobilegateway.wellness.incloud.it/api/v1/Wic_FitExpress/"
DAYS_AHEAD = 2            # alla mezzanotte del giorno D si apre D+2
LEAD = 0.15               # s: invia il primo tentativo appena prima della mezzanotte server
RETRY = 0.25              # s tra tentativi
MAX_RETRY_S = 180
MAX_WAIT_S = 2 * 3600     # non attendere piu' di 2 ore
WD = {"lunedi":0,"martedi":1,"mercoledi":2,"giovedi":3,"venerdi":4,"sabato":5,"domenica":6,
      "monday":0,"tuesday":1,"wednesday":2,"thursday":3,"friday":4,"saturday":5,"sunday":6}

def log(*a):
    print(dt.datetime.now(ROME).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], *a, flush=True)

class Client:
    def __init__(s):
        s.S = requests.Session()
        s.S.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=8))
        s.H = {"applicationVersion":"1.3.1","platform":"android","lang":"it","Content-Type":"application/json"}
        s.offset = 0.0
    def login(s):
        r = s.S.post(BASE+"authenticate", json={"email":os.environ["FITEXPRESS_EMAIL"],
                     "password":os.environ["FITEXPRESS_PASSWORD"]}, headers=s.H, timeout=20)
        r.raise_for_status(); j = r.json()
        ci = (j.get("userInfo") or {}).get("currentInstallation") or {}
        s.H["Authorization"] = "Bearer " + j["accessToken"]
        s.H["installationKey"] = ci.get("webInstallationKey") or ci.get("installationKey") or ""
        log("login OK")
    def get(s, path, **kw):
        r = s.S.get(BASE+path, headers=s.H, timeout=15, **kw); r.raise_for_status(); return r
    def sync_clock(s, n=5):
        """Stima offset server-locale. Il header Date ha risoluzione 1s: si cerca il cambio di secondo."""
        best = None; prev = None
        for _ in range(40):
            t0 = time.time(); r = s.S.get(BASE+"calendar/my", headers=s.H, timeout=10); t1 = time.time()
            d = r.headers.get("Date")
            if not d: break
            sec = parsedate_to_datetime(d).timestamp()
            if prev is not None and sec != prev:   # secondo appena scattato: server ~ sec (+0..rtt)
                best = sec - (t0 + t1) / 2 + 0.0; break
            prev = sec; time.sleep(0.1)
        if best is None and prev is not None: best = prev + 0.5 - (t0 + t1) / 2
        s.offset = best or 0.0
        log(f"offset server-locale stimato {s.offset:+.3f}s")
    def server_now(s): return time.time() + s.offset

def walk(o):
    if isinstance(o, dict):
        if "eventId" in o or "idEvent" in o: yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)

def find_event(c, day, name, start):
    data = c.get("calendar/detail", params={"day":day.day,"month":day.month,"year":day.year}).json()
    for e in walk(data):
        title = (e.get("title") or e.get("name") or "").strip().lower()
        st = e.get("startTime") or e.get("eventStart") or ""
        if title == name.strip().lower() and st[11:16] == start:
            return e
    return None

def is_limit(t): return "limit" in t or "giorni" in t
def is_full(t): return any(k in t for k in ("complet","esaurit","full","nessun posto","posti non"))

def book_all(c, targets, deadline):
    """targets: list of dict(eid,name,wl). Tenta in round-robin finche' ok o errore definitivo."""
    pending = {t["eid"]: dict(t, body={}, n=0) for t in targets}
    while pending and time.time() < deadline:
        for eid, t in list(pending.items()):
            t["n"] += 1
            try:
                r = c.S.post(BASE+f"calendar/{eid}", json=t["body"], headers=c.H, timeout=5)
                try: j = r.json(); txt = json.dumps(j).lower()
                except Exception: j = None; txt = r.text.lower()
                ok = r.ok and not (isinstance(j, dict) and j.get("success") is False)
                if ok:
                    log(f"PRENOTATO {t['name']} (event {eid}) tentativo {t['n']} body={t['body']}"); del pending[eid]; continue
                if t["n"] <= 3 or t["n"] % 20 == 0: log(f"{t['name']} tent. {t['n']} -> {r.status_code} {txt[:250]}")
                if is_limit(txt) or r.status_code >= 500 or r.status_code == 429: continue
                if is_full(txt) and t["wl"] and not t["body"]:
                    log(f"{t['name']} pieno -> lista d'attesa"); t["body"] = {"waitingList": True}; continue
                log(f"{t['name']} errore definitivo: {r.status_code} {txt[:400]}"); del pending[eid]
            except Exception as x:
                log(f"{t['name']} errore rete {x}")
        time.sleep(RETRY)
    for t in pending.values(): log(f"NON prenotato {t['name']} (timeout)")
    return not pending

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--now", action="store_true")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "courses.yaml"))
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))["courses"]
    now = dt.datetime.now(ROME)
    # Mezzanotte target: la prossima (se siamo la sera) o quella appena passata (run in ritardo)
    mid_date = now.date() + dt.timedelta(days=1) if now.hour >= 12 else now.date()
    if a.now or a.dry_run: mid_date = now.date()
    midnight = dt.datetime.combine(mid_date, dt.time(), ROME)
    target_day = mid_date + dt.timedelta(days=DAYS_AHEAD)
    todo = [c for c in cfg if WD[str(c["weekday"]).lower().replace("ì","i")] == target_day.weekday()]
    log(f"mezzanotte {midnight.isoformat()} -> giorno prenotabile {target_day} ; corsi: {[c['name'] for c in todo]}")
    if not todo: log("nessun corso da prenotare"); return 0
    if not a.now and not a.dry_run and midnight.timestamp() - time.time() > MAX_WAIT_S:
        log("troppo presto (>2h alla mezzanotte), esco"); return 0
    if not a.now and not a.dry_run and time.time() - midnight.timestamp() > 600:
        log("mezzanotte passata da oltre 10 min (run duplicato/ora legale), esco"); return 0
    c = Client(); c.login()
    targets = []
    for x in todo:
        e = find_event(c, target_day, x["name"], str(x["start"]))
        if not e: log(f"corso non trovato: {x['name']} {x['start']} {target_day}"); continue
        log(f"trovato {x['name']} {x['start']} eventId={e['eventId']} posti={e.get('availableNumber')}")
        targets.append({"eid": e["eventId"], "name": f"{x['name']} {x['start']}", "wl": bool(x.get("waiting_list", True))})
    if a.dry_run or not targets: return 0
    if not a.now:
        c.sync_clock()
        fire = midnight.timestamp() - LEAD   # in orario server
        warm = 0; relog = False
        while c.server_now() < fire:
            rem = fire - c.server_now()
            if rem > 120 and not relog and rem < 600: c.login(); relog = True  # token fresco
            if time.time() - warm > 15 and rem > 1.5:
                try: c.get("calendar/my")
                except Exception as x: log("warm-up err", x)
                warm = time.time()
            time.sleep(min(0.5, max(rem - 0.02, 0.001)) if rem > 0.05 else 0.001)
        log("VIA")
    ok = book_all(c, targets, time.time() + MAX_RETRY_S)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
