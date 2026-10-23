"""Concrete test settings from recorded executed bids, never a CPC-to-bid shortcut."""
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def execution_dates(value):
    """Exclude both possible change dates for legacy timestamps without a zone."""
    try:
        stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    except (ValueError, AttributeError):
        return set()
    if stamp.tzinfo:
        return {stamp.astimezone(ZoneInfo('America/Los_Angeles')).date()}
    return {stamp.date(),stamp.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('America/Los_Angeles')).date()}


def recorded_bid_assessment(target, facts, changes, cutoff, brand_days, excluded_days=(), company_context=None, asof=None, attribution_days=7):
    identity = ('brand','campaign_name','ad_group_name','match_type')
    events=[]
    for row in changes:
        if (any(row.get(k)!=target.get(k) for k in identity)
            or row.get('entity_name')!=target['target'] or not row.get('executed_at')
            or row.get('intervention_type')!='ppc_action' or 'bid' not in str(row.get('action_type',''))):
            continue
        try:
            bid=float(row['new_value'])
        except (TypeError,ValueError,KeyError):
            continue
        days=execution_dates(row['executed_at'])
        if not days or not math.isfinite(bid) or bid<=0:
            continue
        events.append(dict(row,bid=bid,transition=days))
    events.sort(key=lambda r:r['executed_at'])
    all_events=events
    cutoff_day=date.fromisoformat(cutoff)
    events=[e for e in all_events if max(e['transition'])<=cutoff_day]
    known_events=[e for e in all_events if max(e['transition'])<=date.fromisoformat(asof or cutoff)]
    empty={'available':False,'reason':'No exact-scope executed bid record; no bid amount is invented','runs':[]}
    if not events:
        return empty
    excluded={date.fromisoformat(str(d)) for d in excluded_days}
    excluded |= {d for event in events for d in event['transition']}
    available={date.fromisoformat(d) for d in brand_days if d<=cutoff}
    daily=defaultdict(lambda:dict(clicks=0.,impressions=0.,spend=0.,ad_sales=0.,ad_orders=0.))
    for row in facts:
        if row['report_date']>cutoff:
            continue
        for key in daily[row['report_date']]:daily[row['report_date']][key]+=float(row.get(key) or 0)
    runs=[]
    def append_run(bid,start,end,kind,record):
        days=sorted(d.isoformat() for d in available if start<=d<=end and d not in excluded)
        if days:
            runs.append(dict(bid=bid,start=start.isoformat(),end=end.isoformat(),dates=days,
                source=kind,record_id=record.get('audit_id',record.get('id')),
                execution=record['executed_at'],totals={k:sum(daily[d][k] for d in days) for k in ('clicks','impressions','spend','ad_sales','ad_orders')}))
    # The owner recorded an old bid alongside this exact pre-change baseline.
    # This is weaker evidence than an archived settings snapshot and is labeled.
    first=events[0]
    try:
        old=float(first['old_value']);start=date.fromisoformat(first['period_start'])
        end=min(date.fromisoformat(first['period_end']),min(first['transition'])-timedelta(days=1),cutoff_day)
        if old>0 and start<=end:append_run(old,start,end,'Reported old bid during recorded baseline; configuration persistence unverified',first)
    except (TypeError,ValueError,KeyError):
        pass
    for j,event in enumerate(events):
        start=max(event['transition'])+timedelta(days=1)
        next_event=next((e for e in all_events if e['executed_at']>event['executed_at']),None)
        end=min(cutoff_day,min(next_event['transition'])-timedelta(days=1)) if next_event else cutoff_day
        # A closed/reverted run without a successor has no known stop timestamp.
        if next_event is None and event.get('status') not in {'executed','monitoring'}:
            continue
        append_run(event['bid'],start,end,'Executed record; assumes no unlogged settings change within the run',event)
    latest={}
    for run in runs:
        # Prefer the most recent observed run of each setting, not the best-looking one.
        if run['totals']['clicks'] or run['totals']['spend']:
            latest[run['bid']]=run
    if not latest:
        return dict(empty,reason='Executed bid records exist but no mature outcome data follows them',runs=runs)
    candidates=list(latest.values())
    weekdays=set.intersection(*({date.fromisoformat(d).weekday() for d in run['dates']} for run in candidates))
    if not weekdays:
        return dict(empty,reason='Recorded settings have no comparable reporting weekdays',runs=runs)
    quotas={w:min(sum(date.fromisoformat(d).weekday()==w for d in r['dates']) for r in candidates) for w in weekdays}
    count=sum(quotas.values())
    economics=target['economics']
    for run in candidates:
        matched=sorted(d for w,n in quotas.items() for d in [d for d in run['dates'] if date.fromisoformat(d).weekday()==w][-n:])
        sums={k:sum(daily[d][k] for d in matched) for k in ('clicks','impressions','spend','ad_sales','ad_orders')}
        run.update(matched_dates=matched,matched_days=count,matched=sums,
                   clicks_per_day=sums['clicks']/count,impressions_per_day=sums['impressions']/count,
                   cpc=sums['spend']/sums['clicks'] if sums['clicks'] else None)
        if economics['available']:
            scores=[(sums['ad_sales']*m-sums['spend'])/count for m in (economics['low'],economics['high'])]
            run.update(contribution_low=min(scores),contribution_high=max(scores))
        if company_context:
            company=company_context(matched)
            run['company']={k:company.get(k) for k in ('sales','spend','tacos','contribution','contribution_per_day','days','exact_fee_share')} if company else None
    last=known_events[-1]
    pending=max(last['transition'])>cutoff_day
    can_rank=economics['available'] and economics['complete']
    # Preserve the latest recorded setting with observed orders. A cheaper run
    # with no demand is not a profit improvement or evidence of safe traffic loss.
    productive=[r for r in candidates if r['matched']['ad_orders'] > 0]
    baseline=max(productive or candidates,key=lambda r:r['execution'])
    chosen=baseline
    rejected=[]
    eligible=[]
    for run in candidates:
        if run is baseline:
            continue
        traffic_loss=(run['clicks_per_day'] < baseline['clicks_per_day'] or
                      run['impressions_per_day'] < baseline['impressions_per_day'])
        company=run.get('company') or {}
        base_company=baseline.get('company') or {}
        company_gain=(company.get('contribution_per_day') is not None and
                      base_company.get('contribution_per_day') is not None and
                      company['contribution_per_day'] > base_company['contribution_per_day'])
        # Both margin scenarios must improve; a minimum-margin-only winner can
        # simply be the setting that stopped spending. Company context is an
        # additional check, never an estimate of keyword-caused organic lift.
        direct_gain=(can_rank and run['matched']['ad_orders'] > 0 and
                     run['contribution_low'] > baseline['contribution_low'] and
                     run['contribution_high'] > baseline['contribution_high'])
        if traffic_loss:
            rejected.append(dict(bid=run['bid'],reason='Lower observed traffic; historical company differences do not establish that losing this traffic improves total contribution.'))
        elif not company_gain:
            rejected.append(dict(bid=run['bid'],reason='No matched company-contribution improvement, or company evidence is unavailable.'))
        elif not direct_gain:
            rejected.append(dict(bid=run['bid'],reason='No improvement across both direct contribution scenarios with observed orders.'))
        else:
            eligible.append(run)
    if eligible:
        chosen=max(eligible,key=lambda r:(r['company']['contribution_per_day'],r['execution']))
    alternatives=[r for r in candidates if r is not chosen]
    robust=bool(alternatives and can_rank and
                all(chosen['contribution_low']>r['contribution_high'] for r in alternatives))
    no_profitable_setting = bool(can_rank and all(r['contribution_high'] <= 0 for r in candidates))
    conflict = any(chosen.get('company') and r.get('company') and chosen['company'].get('contribution_per_day') is not None and r['company'].get('contribution_per_day') is not None and chosen['company']['contribution_per_day'] < r['company']['contribution_per_day'] for r in alternatives)
    reason=('Retain the latest recorded setting with orders: no alternative demonstrated better direct economics across both product-mix scenarios, higher matched company contribution and preserved traffic.'
            if chosen is baseline else
            'Historical test candidate improved both direct contribution scenarios and matched company contribution without reducing observed clicks or impressions. Company differences remain observational.')
    recommended=last['bid'] if pending else (chosen['bid'] if can_rank and productive and not no_profitable_setting else None)
    return dict(available=True,recommended_bid=recommended,historical_best_bid=chosen['bid'] if can_rank and not no_profitable_setting else None,pending_latest=pending,pending_review_after=(max(last['transition'])+timedelta(days=attribution_days+2)).isoformat(),no_profitable_setting=no_profitable_setting,company_context_conflict=conflict,comparison_available=bool(alternatives),last_recorded_bid=last['bid'],last_recorded_at=last['executed_at'],
                change_from_recorded=recommended/last['bid']-1 if recommended is not None else None,chosen=chosen,runs=runs,candidates=candidates,
                matched_days=count,robust_mix_comparison=robust,reason=reason,
                baseline_bid=baseline['bid'], rejected_alternatives=rejected, selection_changed=chosen is not baseline, objective='Preserve productive traffic. Change the recorded baseline only when both direct contribution scenarios and matched company contribution improve without lower clicks or impressions. Company results are observational, not attributed lift.',
                limitations='Historical test candidate, not a verified live bid or proven optimum. Weekdays and known promotion/change days are controlled; budget, placement, query mix, product changes and unlogged settings are not isolated. Missing target rows count as zero delivery only on loaded brand-report dates; import completeness remains unverified.')
