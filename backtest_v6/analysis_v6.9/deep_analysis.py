#!/usr/bin/env python3
"""Deep analysis of V6.9 backtest history files.

V6.9 JSON field mapping:
  trade_records[] = executed trades only
  .realized_pnl   = net PnL after charges
  .gross_pnl       = PnL before charges
  .total_charges   = charges for this trade
  .entry_risk_per_share * initial_qty = total risk (for R-multiple)
  .mfe_r, .mae_r   = already in R units
  .bars_in_trade, .hma_trail_active, .be_armed, .trail_armed
  
  summary.closed_trades, .total_return, .total_return_pct
  summary.gross_return_before_charges, .total_charges
"""

import json, os, statistics
from collections import Counter, defaultdict

HISTORY_DIR = os.path.join(os.path.dirname(__file__), '..', 'history_v6.9')
FILES = [
    'backtest_history_28-02-2026_06-04_pm.json',
    'backtest_history_28-02-2026_06-08_pm.json',
    'backtest_history_28-02-2026_07-00_pm.json',
    'backtest_history_28-02-2026_07-24_pm.json',
]

# ── helpers ──────────────────────────────────────────────────────────────────
def pnl(t):  return t.get('realized_pnl', 0) or 0
def gross(t): return t.get('gross_pnl', 0) or 0
def charges(t): return t.get('total_charges', 0) or 0
def r_mult(t):
    risk = (t.get('entry_risk_per_share', 0) or 0) * (t.get('initial_qty', 0) or 0)
    return pnl(t) / risk if risk > 0 else 0
def trades_of(d): return d.get('trade_records', [])
def mean_safe(lst): return statistics.mean(lst) if lst else 0
def median_safe(lst): return statistics.median(lst) if lst else 0

# ── load ─────────────────────────────────────────────────────────────────────
def load_all():
    data = {}
    for fname in FILES:
        path = os.path.join(HISTORY_DIR, fname)
        with open(path) as f: d = json.load(f)
        cfg = d.get('config_snapshot', {})
        hf, hs = cfg.get('V6_6_HMA_FAST','?'), cfg.get('V6_6_HMA_SLOW','?')
        run = d.get('run', {}); inp = d.get('inputs', {})
        start = inp.get('start_date') or run.get('start_date','?')
        end   = inp.get('end_date')   or run.get('end_date','?')
        year  = start[:4] if isinstance(start, str) and len(start)>=4 else '?'
        label = f"HMA_{hf}_{hs}_{year}"
        data[label] = d
        print(f"Loaded: {fname} -> {label}  ({start} -> {end})  freshness={cfg.get('V6_7_CROSS_FRESHNESS_BARS')}")
    return data

# ── 1. Summary ───────────────────────────────────────────────────────────────
def summary_comparison(data):
    print("\n" + "="*110)
    print("SUMMARY COMPARISON")
    print("="*110)
    hdr = f"{'Label':<22} {'Trades':>6} {'WinR%':>6} {'NetPnL':>12} {'GrossPnL':>12} {'Charges':>10} {'ChgPct':>7} {'Return%':>8} {'PF':>5} {'AvgR':>6}"
    print(hdr); print("-"*len(hdr))
    for label, d in data.items():
        s = d.get('summary', {}); trs = trades_of(d)
        net = s.get('total_return', 0)
        grs = s.get('gross_return_before_charges', 0)
        chg = s.get('total_charges', 0)
        wins = sum(1 for t in trs if pnl(t) > 0)
        n = len(trs); wr = wins/n*100 if n else 0
        pos = sum(pnl(t) for t in trs if pnl(t)>0)
        neg = abs(sum(pnl(t) for t in trs if pnl(t)<0))
        pf = pos/neg if neg>0 else 0
        avgr = mean_safe([r_mult(t) for t in trs])
        cpct = chg/grs*100 if grs>0 else 0
        print(f"{label:<22} {n:>6} {wr:>5.1f}% {net:>12,.0f} {grs:>12,.0f} {chg:>10,.0f} {cpct:>6.1f}% {s.get('total_return_pct',0):>7.2f}% {pf:>5.2f} {avgr:>6.3f}")

# ── 2. Exit Reason ───────────────────────────────────────────────────────────
def exit_reason_analysis(data):
    print("\n" + "="*110)
    print("EXIT REASON BREAKDOWN")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        if not trs: continue
        stats = defaultdict(lambda: dict(count=0,wins=0,pnl=0,r=[],bars=[],mfe=[],mae=[]))
        for t in trs:
            reason = t.get('exit_reason','?')
            p = pnl(t)
            s = stats[reason]; s['count']+=1
            if p>0: s['wins']+=1
            s['pnl']+=p; s['r'].append(r_mult(t))
            s['bars'].append(t.get('bars_in_trade',0))
            s['mfe'].append(t.get('mfe_r',0)); s['mae'].append(t.get('mae_r',0))
        print(f"\n--- {label} ({len(trs)} trades) ---")
        print(f"  {'Exit':<20} {'Cnt':>5} {'%':>5} {'WinR':>6} {'NetPnL':>12} {'AvgR':>7} {'Bars':>6} {'MFE':>6} {'MAE':>6}")
        for reason in sorted(stats, key=lambda x: stats[x]['count'], reverse=True):
            s=stats[reason]; c=s['count']
            print(f"  {reason:<20} {c:>5} {c/len(trs)*100:>4.0f}% {s['wins']/c*100:>5.1f}% {s['pnl']:>12,.0f} {mean_safe(s['r']):>7.3f} {mean_safe(s['bars']):>6.1f} {mean_safe(s['mfe']):>6.2f} {mean_safe(s['mae']):>6.2f}")

# ── 3. Stop Loss Deep-Dive ──────────────────────────────────────────────────
def stop_loss_deep_dive(data):
    print("\n" + "="*110)
    print("STOP LOSS DEEP DIVE")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        stopped = [t for t in trs if t.get('exit_reason')=='STOP_HARD']
        if not stopped: continue
        mfes = [t.get('mfe_r',0) for t in stopped]
        bars = [t.get('bars_in_trade',0) for t in stopped]
        hi_mfe = [t for t in stopped if t.get('mfe_r',0)>=1.0]
        quick  = [t for t in stopped if t.get('bars_in_trade',0)<=2]
        lng = sum(1 for t in stopped if t.get('direction')=='LONG')
        sht = len(stopped)-lng
        stop_pnl = sum(pnl(t) for t in stopped)
        print(f"\n--- {label}: {len(stopped)} STOP_HARD trades (total loss: {stop_pnl:,.0f}) ---")
        print(f"  MFE: mean={mean_safe(mfes):.3f}R median={median_safe(mfes):.3f}R")
        print(f"  Bars: mean={mean_safe(bars):.1f} median={median_safe(bars):.0f}")
        print(f"  MFE>=1R (had profit): {len(hi_mfe)} ({len(hi_mfe)/len(stopped)*100:.0f}%)")
        print(f"  Quick stops (<=2 bars): {len(quick)} ({len(quick)/len(stopped)*100:.0f}%)")
        print(f"  LONG: {lng}, SHORT: {sht}")
        sect_stops = Counter(t.get('sector','?') for t in stopped)
        sect_total = Counter(t.get('sector','?') for t in trs)
        print(f"  Sector stop rates:")
        for sec, cnt in sect_stops.most_common():
            tot = sect_total.get(sec,1)
            sec_stop_pnl = sum(pnl(t) for t in stopped if t.get('sector')==sec)
            print(f"    {sec:<25} {cnt}/{tot} ({cnt/tot*100:.0f}%)  PnL: {sec_stop_pnl:>10,.0f}")

# ── 4. HMA Trail System ─────────────────────────────────────────────────────
def hma_trail_analysis(data):
    print("\n" + "="*110)
    print("HMA TRAIL SYSTEM ANALYSIS")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        trail_on  = [t for t in trs if t.get('hma_trail_active')]
        trail_off = [t for t in trs if not t.get('hma_trail_active')]
        be_armed  = [t for t in trs if t.get('be_armed')]
        print(f"\n--- {label} ---")
        print(f"  Trail Active: {len(trail_on)}/{len(trs)} ({len(trail_on)/len(trs)*100:.1f}%)")
        print(f"  BE Armed:     {len(be_armed)}/{len(trs)} ({len(be_armed)/len(trs)*100:.1f}%)")
        for lbl, subset in [('Trail ON', trail_on), ('Trail OFF', trail_off)]:
            if not subset: continue
            sp = sum(pnl(t) for t in subset)
            sw = sum(1 for t in subset if pnl(t)>0)
            print(f"  {lbl}: {len(subset)} trades, WinR={sw/len(subset)*100:.1f}%, PnL={sp:>12,.0f}, AvgR={mean_safe([r_mult(t) for t in subset]):.3f}")

# ── 5. Brokerage Impact ─────────────────────────────────────────────────────
def brokerage_impact(data):
    print("\n" + "="*110)
    print("BROKERAGE IMPACT ANALYSIS")
    print("="*110)
    for label, d in data.items():
        s = d.get('summary', {}); trs = trades_of(d)
        grs = s.get('gross_return_before_charges', 0)
        chg = s.get('total_charges', 0)
        net = s.get('total_return', 0)
        turnover = s.get('total_turnover', 0)
        print(f"\n--- {label} ---")
        print(f"  Gross PnL:  {grs:>12,.0f}")
        print(f"  Charges:    {chg:>12,.0f} ({chg/grs*100:.1f}% of gross)" if grs>0 else f"  Charges: {chg:>12,.0f}")
        print(f"  Net PnL:    {net:>12,.0f}")
        print(f"  Turnover:   {turnover:>12,.0f}")
        if grs>0 and chg/grs>0.30:
            print(f"  *** WARNING: Charges eating {chg/grs*100:.1f}% of gross profits ***")
        # How many trades flipped by charges?
        profitable_gross = sum(1 for t in trs if gross(t)>0)
        profitable_net   = sum(1 for t in trs if pnl(t)>0)
        print(f"  Trades profit (gross): {profitable_gross}/{len(trs)}, (net): {profitable_net}/{len(trs)}")
        flipped = sum(1 for t in trs if gross(t)>0 and pnl(t)<=0)
        print(f"  Flipped to loss by charges: {flipped} trades")
        if trs:
            print(f"  Avg charge/trade: {chg/len(trs):,.0f}")

# ── 6. Holding Period ────────────────────────────────────────────────────────
def bars_in_trade_analysis(data):
    print("\n" + "="*110)
    print("HOLDING PERIOD (BARS IN TRADE) ANALYSIS")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        w_bars = [t.get('bars_in_trade',0) for t in trs if pnl(t)>0]
        l_bars = [t.get('bars_in_trade',0) for t in trs if pnl(t)<=0]
        print(f"\n--- {label} ---")
        if w_bars: print(f"  Winners: mean={mean_safe(w_bars):.1f} bars, median={median_safe(w_bars):.0f}")
        if l_bars: print(f"  Losers:  mean={mean_safe(l_bars):.1f} bars, median={median_safe(l_bars):.0f}")
        buckets = [(0,3,'Very Short 0-3'),(4,10,'Short 4-10'),(11,20,'Medium 11-20'),(21,999,'Long 21+')]
        print(f"  {'Bucket':<20} {'Count':>6} {'WinR%':>7} {'NetPnL':>12} {'AvgPnL':>10} {'AvgR':>7}")
        for lo,hi,name in buckets:
            bt = [t for t in trs if lo<=t.get('bars_in_trade',0)<=hi]
            if bt:
                c=len(bt); w=sum(1 for t in bt if pnl(t)>0)
                p=sum(pnl(t) for t in bt)
                print(f"  {name:<20} {c:>6} {w/c*100:>6.1f}% {p:>12,.0f} {p/c:>10,.0f} {mean_safe([r_mult(t) for t in bt]):>7.3f}")

# ── 7. Direction Analysis ────────────────────────────────────────────────────
def direction_analysis(data):
    print("\n" + "="*110)
    print("DIRECTION (LONG vs SHORT) ANALYSIS")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        for dirn in ['LONG','SHORT']:
            dt = [t for t in trs if t.get('direction')==dirn]
            if not dt: continue
            c=len(dt); w=sum(1 for t in dt if pnl(t)>0)
            p=sum(pnl(t) for t in dt)
            ar=mean_safe([r_mult(t) for t in dt])
            ab=mean_safe([t.get('bars_in_trade',0) for t in dt])
            print(f"\n--- {label} | {dirn}: {c} trades, WinR={w/c*100:.1f}%, PnL={p:>12,.0f}, AvgR={ar:.3f}, AvgBars={ab:.1f} ---")
            exits = Counter(t.get('exit_reason','?') for t in dt)
            for reason, cnt in exits.most_common():
                rp = sum(pnl(t) for t in dt if t.get('exit_reason')==reason)
                print(f"    {reason:<20}: {cnt} trades, PnL: {rp:>10,.0f}")

# ── 8. MFE Leakage ──────────────────────────────────────────────────────────
def mfe_leakage_analysis(data):
    print("\n" + "="*110)
    print("MFE LEAKAGE (How much peak profit is captured?)")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        mfes = [t.get('mfe_r',0) for t in trs]
        rs   = [r_mult(t) for t in trs]
        caps = [r_mult(t)/t.get('mfe_r',0) for t in trs if t.get('mfe_r',0)>0]
        print(f"\n--- {label} ---")
        print(f"  Avg MFE: {mean_safe(mfes):.3f}R, Avg actual R: {mean_safe(rs):.3f}R")
        if caps:
            print(f"  Capture ratio: mean={mean_safe(caps)*100:.1f}%, median={median_safe(caps)*100:.1f}%")
        big = [t for t in trs if t.get('mfe_r',0)>=3.0]
        if big:
            bm = mean_safe([t['mfe_r'] for t in big])
            br = mean_safe([r_mult(t) for t in big])
            lost = sum(1 for t in big if r_mult(t)<0)
            print(f"  Big runners (MFE>=3R): {len(big)} trades, avgMFE={bm:.2f}R, captured={br:.2f}R ({br/bm*100:.0f}%)")
            print(f"    Turned into LOSSES: {lost} ({lost/len(big)*100:.0f}%)")

# ── 9. Time of Day ──────────────────────────────────────────────────────────
def time_of_day_analysis(data):
    print("\n" + "="*110)
    print("TIME-OF-DAY ANALYSIS")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        buckets = defaultdict(lambda: dict(count=0,wins=0,pnl=0))
        for t in trs:
            et = t.get('entry_time','')
            if not et: continue
            try:
                tp = et.split('T')[1] if 'T' in et else et.split(' ')[1]
                h,m = int(tp.split(':')[0]), int(tp.split(':')[1])
                if h<10: b='09:15-10:00'
                elif h<11: b='10:00-11:00'
                elif h<12: b='11:00-12:00'
                elif h<13: b='12:00-13:00'
                elif h<14: b='13:00-14:00'
                else: b='14:00-15:30'
            except: b='??'
            s=buckets[b]; s['count']+=1
            if pnl(t)>0: s['wins']+=1
            s['pnl']+=pnl(t)
        print(f"\n--- {label} ---")
        print(f"  {'Time':<15} {'Count':>6} {'WinR%':>7} {'NetPnL':>12} {'AvgPnL':>10}")
        for b in sorted(buckets):
            s=buckets[b]; c=s['count']
            print(f"  {b:<15} {c:>6} {s['wins']/c*100:>6.1f}% {s['pnl']:>12,.0f} {s['pnl']/c:>10,.0f}")

# ── 10. Monthly Performance ─────────────────────────────────────────────────
def monthly_performance(data):
    print("\n" + "="*110)
    print("MONTHLY PERFORMANCE BREAKDOWN")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        monthly = defaultdict(lambda: dict(count=0,wins=0,pnl=0,stops=0,gross=0))
        for t in trs:
            et = t.get('entry_time','')
            if not et: continue
            mo = et[:7]
            s=monthly[mo]; s['count']+=1
            if pnl(t)>0: s['wins']+=1
            s['pnl']+=pnl(t); s['gross']+=gross(t)
            if t.get('exit_reason')=='STOP_HARD': s['stops']+=1
        print(f"\n--- {label} ---")
        print(f"  {'Month':<10} {'Trades':>7} {'WinR%':>7} {'GrossPnL':>12} {'NetPnL':>12} {'StopRate':>9}")
        for mo in sorted(monthly):
            s=monthly[mo]; c=s['count']
            print(f"  {mo:<10} {c:>7} {s['wins']/c*100:>6.1f}% {s['gross']:>12,.0f} {s['pnl']:>12,.0f} {s['stops']/c*100:>8.1f}%")

# ── 11. Winner vs Loser Profile ─────────────────────────────────────────────
def winner_loser_profile(data):
    print("\n" + "="*110)
    print("WINNER vs LOSER PROFILE")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        winners = [t for t in trs if pnl(t)>0]
        losers  = [t for t in trs if pnl(t)<=0]
        print(f"\n--- {label}: {len(winners)}W / {len(losers)}L ---")
        print(f"  {'Metric':<30} {'Winners':>15} {'Losers':>15}")
        print(f"  {'-'*60}")
        for name, fn in [
            ('Count', lambda s: str(len(s))),
            ('Avg PnL', lambda s: f"{mean_safe([pnl(t) for t in s]):>12,.0f}"),
            ('Avg R', lambda s: f"{mean_safe([r_mult(t) for t in s]):.3f}"),
            ('Avg bars_in_trade', lambda s: f"{mean_safe([t.get('bars_in_trade',0) for t in s]):.1f}"),
            ('Avg MFE(R)', lambda s: f"{mean_safe([t.get('mfe_r',0) for t in s]):.3f}"),
            ('Avg MAE(R)', lambda s: f"{mean_safe([t.get('mae_r',0) for t in s]):.3f}"),
            ('HMA trail active %', lambda s: f"{sum(1 for t in s if t.get('hma_trail_active'))/len(s)*100:.1f}%" if s else '0%'),
            ('BE armed %', lambda s: f"{sum(1 for t in s if t.get('be_armed'))/len(s)*100:.1f}%" if s else '0%'),
            ('LONG %', lambda s: f"{sum(1 for t in s if t.get('direction')=='LONG')/len(s)*100:.1f}%" if s else '0%'),
        ]:
            print(f"  {name:<30} {fn(winners):>15} {fn(losers):>15}")
        # Exit reason comparison
        print(f"  {'--- Exit Reasons ---':<30} {'Winners':>15} {'Losers':>15}")
        all_reasons = set(t.get('exit_reason','?') for t in trs)
        for reason in sorted(all_reasons):
            wc = sum(1 for t in winners if t.get('exit_reason')==reason)
            lc = sum(1 for t in losers if t.get('exit_reason')==reason)
            if wc+lc > 0:
                print(f"  {reason:<30} {wc:>15} {lc:>15}")

# ── 12. Consecutive Loss Streaks ─────────────────────────────────────────────
def consecutive_loss_analysis(data):
    print("\n" + "="*110)
    print("CONSECUTIVE LOSS STREAKS")
    print("="*110)
    for label, d in data.items():
        trs = sorted(trades_of(d), key=lambda t: t.get('entry_time',''))
        max_streak=0; cur=0; cur_pnl=0; streaks=[]; max_pnl=0
        for t in trs:
            if pnl(t)<=0:
                cur+=1; cur_pnl+=pnl(t)
            else:
                if cur>0: streaks.append((cur, cur_pnl))
                if cur>max_streak: max_streak=cur; max_pnl=cur_pnl
                cur=0; cur_pnl=0
        if cur>0: streaks.append((cur,cur_pnl))
        if cur>max_streak: max_streak=cur; max_pnl=cur_pnl
        print(f"\n--- {label} ---")
        print(f"  Max consecutive losses: {max_streak} (PnL: {max_pnl:,.0f})")
        big = [s for s in streaks if s[0]>=3]
        print(f"  Streaks >= 3 losses: {len(big)}")
        if streaks:
            print(f"  Avg streak length: {mean_safe([s[0] for s in streaks]):.1f}")

# ── 13. Sector Comparison ───────────────────────────────────────────────────
def sector_comparison(data):
    print("\n" + "="*110)
    print("SECTOR PERFORMANCE COMPARISON")
    print("="*110)
    all_sectors = set()
    sdm = {}
    for label, d in data.items():
        trs = trades_of(d)
        ss = defaultdict(lambda: dict(count=0,wins=0,pnl=0,bars=[]))
        for t in trs:
            sec = t.get('sector','?'); all_sectors.add(sec)
            s=ss[sec]; s['count']+=1
            if pnl(t)>0: s['wins']+=1
            s['pnl']+=pnl(t); s['bars'].append(t.get('bars_in_trade',0))
        sdm[label] = ss
    labels = list(data.keys())
    print(f"\n{'Sector':<22}", end='')
    for l in labels: print(f" | {l:>10}(T/WR%/PnL)", end='')
    print()
    print("-"*150)
    for sec in sorted(all_sectors):
        print(f"{sec:<22}", end='')
        for l in labels:
            s = sdm[l].get(sec, dict(count=0,wins=0,pnl=0,bars=[]))
            c=s['count']; wr=s['wins']/c*100 if c else 0
            print(f" | {c:>3}/{wr:>5.1f}%/{s['pnl']:>10,.0f}", end='')
        print()

# ── 14. Quality Gate Analysis ────────────────────────────────────────────────
def quality_gate_analysis(data):
    print("\n" + "="*110)
    print("QUALITY GATE ANALYSIS (from summary)")
    print("="*110)
    for label, d in data.items():
        s = d.get('summary', {})
        print(f"\n--- {label} ---")
        print(f"  All A-grade signals: {s.get('all_a_grade_signals',0)}")
        print(f"  Executed:            {s.get('closed_trades',0)}")
        print(f"  Gate rejections:")
        for gate in ['gate_slope_blocked','gate_freshness_blocked','gate_price_align_blocked',
                      'gate_separation_blocked','gate_divergence_blocked']:
            val = s.get(gate, 0)
            if val: print(f"    {gate}: {val:,}")
        print(f"  Alignment blocked:   {s.get('alignment_blocked_count',0):,}")
        # Decision breakdown
        dc = s.get('decision_counts', {})
        if dc:
            print(f"  Decision breakdown:")
            for k,v in dc.items():
                print(f"    {k}: {v}")

# ── 15. Signal HMA Quality on Executed Trades ───────────────────────────────
def signal_hma_quality(data):
    print("\n" + "="*110)
    print("HMA QUALITY METRICS ON EXECUTED SIGNALS")
    print("="*110)
    for label, d in data.items():
        signals = d.get('signal_records', [])
        executed = [s for s in signals if s.get('executed_trade')]
        if not executed: continue
        # Match signals to trades by trade_id
        trade_map = {t.get('trade_id'):t for t in trades_of(d)}
        
        slopes_fast=[]; slopes_slow=[]; seps=[]; cross_ages=[]; diverging_pnl={'div':[],'conv':[]}
        for sig in executed:
            hq = sig.get('hma_quality', {})
            if not hq: continue
            slopes_fast.append(hq.get('slope_fast',0))
            slopes_slow.append(hq.get('slope_slow',0))
            seps.append(hq.get('sep_atr_frac',0))
            cross_ages.append(hq.get('cross_bars_ago',0))
            tid = sig.get('executed_trade_id')
            trade = trade_map.get(tid)
            if trade:
                p = pnl(trade)
                if hq.get('is_diverging'):
                    diverging_pnl['div'].append(p)
                else:
                    diverging_pnl['conv'].append(p)
        
        print(f"\n--- {label} ({len(executed)} executed signals) ---")
        print(f"  Slope fast: mean={mean_safe(slopes_fast):.4f}, median={median_safe(slopes_fast):.4f}")
        print(f"  Slope slow: mean={mean_safe(slopes_slow):.4f}, median={median_safe(slopes_slow):.4f}")
        print(f"  Separation/ATR: mean={mean_safe(seps):.3f}, median={median_safe(seps):.3f}")
        print(f"  Cross freshness: mean={mean_safe(cross_ages):.1f} bars")
        # Diverging vs converging
        dv = diverging_pnl['div']; cv = diverging_pnl['conv']
        if dv:
            dw = sum(1 for x in dv if x>0)
            print(f"  DIVERGING signals: {len(dv)} trades, WinR={dw/len(dv)*100:.1f}%, PnL={sum(dv):>12,.0f}")
        if cv:
            cw = sum(1 for x in cv if x>0)
            print(f"  CONVERGING signals: {len(cv)} trades, WinR={cw/len(cv)*100:.1f}%, PnL={sum(cv):>12,.0f}")

# ── 16. Charge Breakdown ────────────────────────────────────────────────────
def charge_breakdown(data):
    print("\n" + "="*110)
    print("CHARGE BREAKDOWN PER RUN")
    print("="*110)
    for label, d in data.items():
        trs = trades_of(d)
        totals = defaultdict(float)
        for t in trs:
            bd = t.get('brokerage_breakdown', {})
            for k,v in bd.items():
                totals[k] += v
        print(f"\n--- {label} ---")
        grand = sum(totals.values())
        for k in ['brokerage','stt','transaction_charge','sebi_charge','stamp_charge','gst']:
            v = totals.get(k, 0)
            pct = v/grand*100 if grand>0 else 0
            print(f"  {k:<22}: {v:>10,.0f} ({pct:>5.1f}%)")
        print(f"  {'TOTAL':<22}: {grand:>10,.0f}")

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("="*110)
    print("V6.9 DEEP BACKTEST ANALYSIS - ALL RUNS")
    print("="*110)
    data = load_all()
    
    summary_comparison(data)
    exit_reason_analysis(data)
    stop_loss_deep_dive(data)
    hma_trail_analysis(data)
    brokerage_impact(data)
    charge_breakdown(data)
    bars_in_trade_analysis(data)
    direction_analysis(data)
    mfe_leakage_analysis(data)
    time_of_day_analysis(data)
    monthly_performance(data)
    winner_loser_profile(data)
    consecutive_loss_analysis(data)
    sector_comparison(data)
    quality_gate_analysis(data)
    signal_hma_quality(data)
    
    print("\n" + "="*110)
    print("ANALYSIS COMPLETE")
    print("="*110)

if __name__ == '__main__':
    main()
