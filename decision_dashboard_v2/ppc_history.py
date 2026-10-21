"""Historical paid-economics assessment, independent of current base-bid access.

Model choices are tested with forward-only monthly forecasts. Economics are
explicit product-mix scenarios, not keyword-level realized or incremental profit.
"""
import math
from collections import defaultdict


def aggregate(rows):
    return {k: sum(float(r.get(k) or 0) for r in rows)
            for k in ('clicks', 'ad_orders', 'ad_sales', 'spend')}


def product_margin_scenarios(conn, brand, asof):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    empty = {'available': False, 'reason': 'Product economics are unavailable', 'products': []}
    if not {'sales_profitability', 'dim_product'} <= tables:
        return empty
    columns = {r[1] for r in conn.execute('PRAGMA table_info(sales_profitability)')}
    required = {'asin', 'sale_date', 'item_price_revenue', 'contribution_profit_before_ads', 'fee_status', 'cogs_amount'}
    if not required <= columns:
        return empty
    product_columns = {r[1] for r in conn.execute('PRAGMA table_info(dim_product)')}
    asof_filter = ' AND (first_observed_date IS NULL OR first_observed_date<=?)' if 'first_observed_date' in product_columns else ''
    products = {r['asin'] for r in conn.execute('SELECT asin FROM dim_product WHERE canonical_brand=? AND is_current=1'+asof_filter, (brand,asof) if asof_filter else (brand,))}
    rows = conn.execute('''SELECT s.asin,substr(s.sale_date,1,7) month,
        SUM(s.item_price_revenue) revenue,SUM(s.contribution_profit_before_ads) contribution,
        MIN(s.sale_date) first,MAX(s.sale_date) last
        FROM sales_profitability s JOIN dim_product p ON p.asin=s.asin AND p.is_current=1
        WHERE p.canonical_brand=? AND s.sale_date<=? AND s.item_price_revenue>0
        AND s.fee_status='exact_order_fee_allocated' AND s.cogs_amount IS NOT NULL
        AND s.contribution_profit_before_ads IS NOT NULL
        GROUP BY s.asin,substr(s.sale_date,1,7) ORDER BY month DESC''', (brand, asof)).fetchall()
    latest = {}
    for row in rows:
        if row['asin'] not in latest:
            latest[row['asin']] = dict(row, margin=row['contribution']/row['revenue'])
    if not latest:
        return empty
    products |= set(latest)  # Earlier sales are direct evidence a SKU already existed.
    margins = [r['margin'] for r in latest.values()]
    return {'available': True, 'low': min(margins), 'high': max(margins),
            'products': sorted(latest.values(), key=lambda r:r['asin']),
            'covered_products': len(latest), 'catalog_products': len(products),
            'complete': set(latest) == products,
            'first': min(r['first'] for r in latest.values()), 'last': max(r['last'] for r in latest.values()),
            'basis': 'Latest available month per SKU, exact order fees and recorded COGS; unknown purchased mix is tested across the observed SKU margin range'}


def _predictive_loss(orders, clicks, alpha, beta):
    # Negative-binomial posterior predictive probability of held-out order count.
    return -(math.lgamma(orders+alpha)-math.lgamma(alpha)-math.lgamma(orders+1)
             +alpha*math.log(beta/(beta+clicks))+orders*math.log(clicks/(beta+clicks)))


def historical_model(rows, peers, start, cutoff, policy, rate_function, seed):
    """Choose history length on earlier held-out months, never current/future outcomes."""
    earlier = [r for r in rows if r['report_date'] < start and r['report_date'] <= cutoff]
    mature = [r for r in rows if start <= r['report_date'] <= cutoff]
    earlier_peers = [r for r in peers if r['report_date'] < start and r['report_date'] <= cutoff]
    buckets = defaultdict(list)
    for row in earlier:
        buckets[row['report_date'][:7]].append(row)
    months = sorted(buckets)
    monthly = [dict(month=m, **aggregate(buckets[m])) for m in months]
    peer_months = defaultdict(list)
    for r in earlier_peers:
        peer_months[r['report_date'][:7]].append(r)
    peer_sums = {m: aggregate(v) for m,v in peer_months.items()}
    folds = []
    for j, test in enumerate(monthly):
        p = {k:sum(v[k] for m,v in peer_sums.items() if m < test['month']) for k in ('clicks','ad_orders')}
        if j and test['clicks'] > 0 and p['clicks'] > 0 and p['ad_orders'] > 0:
            folds.append((j,test,p['ad_orders']/p['clicks']))
    audit_fold = folds[-1] if folds else None
    selection_folds = folds[:-1]
    scores = []
    for length in range(1,len(months)+1):
        losses = []; predicted = actual = 0
        for j,test,peer_rate in selection_folds:
            training = monthly[max(0,j-length):j]
            clicks = sum(r['clicks'] for r in training); orders = sum(r['ad_orders'] for r in training)
            alpha = orders + policy['prior_clicks']*peer_rate
            beta = clicks + policy['prior_clicks']
            losses.append(_predictive_loss(test['ad_orders'],test['clicks'],alpha,beta))
            predicted += test['clicks']*alpha/beta; actual += test['ad_orders']
        if losses:
            scores.append({'months':length,'loss':sum(losses)/len(losses),'folds':len(losses),'predicted_orders':predicted,'actual_orders':actual})
    chosen = min(scores,key=lambda r:(r['loss'],-r['months'])) if scores else None
    length = chosen['months'] if chosen else len(months)
    audit = None
    if audit_fold:
        j,test,peer_rate = audit_fold
        training = monthly[max(0,j-length):j]
        alpha = sum(r['ad_orders'] for r in training) + policy['prior_clicks']*peer_rate
        beta = sum(r['clicks'] for r in training) + policy['prior_clicks']
        audit = {'month':test['month'],'predicted_orders':test['clicks']*alpha/beta,'actual_orders':test['ad_orders'],
                 'loss':_predictive_loss(test['ad_orders'],test['clicks'],alpha,beta),
                 'independent_of_window_selection':True}
    selected = [r for m in months[-length:] for r in buckets[m]] if length else []
    hist = aggregate(selected); peer = aggregate(earlier_peers); now = aggregate(mature)
    source = hist if hist['clicks'] > 0 and hist['ad_orders'] > 0 else peer
    effective_policy = dict(policy, prior_clicks=min(policy['prior_clicks'],source['clicks']))
    rate = rate_function(now['clicks'],now['ad_orders'],source['clicks'],source['ad_orders'],effective_policy,seed)
    # AOV is a documented approximation; uncertainty here does not cover future mix changes.
    prior_orders = effective_policy['prior_clicks'] * source['ad_orders']/source['clicks'] if source['clicks'] else 0
    historical_aov = source['ad_sales']/source['ad_orders'] if source['ad_orders'] else None
    denominator = now['ad_orders']+prior_orders
    aov = (now['ad_sales']+prior_orders*historical_aov)/denominator if denominator and historical_aov is not None else None
    full = aggregate(earlier)
    long_source = full if full['clicks'] and full['ad_orders'] else peer
    long_policy = dict(policy,prior_clicks=min(policy['prior_clicks'],long_source['clicks']))
    long_rate = rate_function(now['clicks'],now['ad_orders'],long_source['clicks'],long_source['ad_orders'],long_policy,seed)
    all_mature = [r for r in rows if r['report_date']<=cutoff]
    return {'available':rate['available'] and aov is not None, 'rate':rate, 'aov':aov,
            'aov_scenarios': sorted({v for v in [aov,historical_aov,full['ad_sales']/full['ad_orders'] if full['ad_orders'] else None,now['ad_sales']/now['ad_orders'] if now['ad_orders'] else None] if v is not None}),
            'history':full, 'long_history_rate':long_rate, 'all_mature':aggregate(all_mature),
            'first': min((r['report_date'] for r in all_mature),default=None),
            'last':max((r['report_date'] for r in all_mature),default=None),
            'history_months':len(months),'selected_months':length,
            'validation':chosen, 'audit':audit, 'validation_candidates':scores,
            'source':'Same exact target history' if source is hist else 'Earlier same-brand, same-match peers',
            'training_first':min((r['report_date'] for r in selected),default=None),
            'training_last':max((r['report_date'] for r in selected),default=None),
            'monthly': monthly}


def assess_paid_economics(target, economics):
    model = target['history_model']
    result = {'available':False,'action':'Review economics','result':'Economics unavailable',
              'reason':'The historical target assessment is available, but product-cost scenarios are missing. Current base bids are not needed for this assessment.'}
    if not model['available']:
        result.update(action='Collect conversion evidence',result='Not enough conversion evidence',reason='No usable earlier target or peer order history exists for a conversion estimate.')
        return result
    if not economics['available']:
        return result
    reference = target['recent'] if target['recent']['clicks'] else target['mature']
    if not reference['clicks']:
        result.update(action='Review inactive target',result='No recent measured traffic',reason='History exists, but no clicks are recorded in the selected mature or recent period. Check current delivery before reactivation.')
        return result
    cpc = reference['spend']/reference['clicks']
    rate = model['rate']; value = model['aov']
    lower, upper = sorted((rate['mean']*value*economics['low'],rate['mean']*value*economics['high']))
    # Extrema cover both rate interval and product-margin scenarios, including negative margins.
    sensitivity_rates = [rate['low'],rate['high']]
    if model['long_history_rate']['available']:
        sensitivity_rates += [model['long_history_rate']['low'],model['long_history_rate']['high']]
    bounds = [r*v*m for r in sensitivity_rates for v in model.get('aov_scenarios',[value]) for m in (economics['low'],economics['high'])]
    uncertain_low,uncertain_high = min(bounds),max(bounds)
    if uncertain_high < cpc:
        verdict,action = 'No — estimated paid loss','Reduce'
        reason = 'Click costs exceed the modeled contribution range. Reduce through a controlled test and watch total sales and traffic.'
    elif uncertain_low > cpc:
        verdict,action = 'Yes — estimated paid contribution','Hold; test expansion'
        reason = 'Modeled contribution per click covers current click cost across the displayed rate interval and observed product-margin scenarios. A profitable average does not prove an increase will pay.'
    elif upper < cpc:
        verdict,action = 'Leans unprofitable','Test reduction'
        reason = 'Historical conversion and product margins suggest these clicks cost too much. Test a reduction; uncertainty is still material.'
    elif lower > cpc:
        verdict,action = 'Promising; still uncertain','Hold'
        reason = 'Historical conversion and product margins suggest these clicks can pay. Hold steady while attribution develops; an increase is not yet established.'
    else:
        verdict,action = 'Depends on purchased mix','Hold; review product mix'
        reason = 'Some observed product-margin scenarios cover click cost and others do not. This is an economic ambiguity, not a missing-base-bid restriction.'
    if not model['all_mature']['clicks']:
        verdict,action = 'No mature target results','Hold — attribution pending'
        reason = 'Earlier peers provide context, but this exact target has no mature clicks. Do not treat a peer estimate as established target performance.'
    if not economics['complete']:
        if action in {'Reduce','Test reduction'}:
            verdict,action = 'Covered-SKU scenario leans unprofitable','Test reduction — partial cost coverage'
        else:
            verdict,action = 'Purchased mix not fully covered','Review mix before expanding'
        reason += ' Only part of the catalog has exact cost evidence; uncovered products can change this conclusion.'
    if target.get('recent_period_present') and not target['recent']['clicks']:
        action = 'Review delivery before changing bid'
        reason += ' No clicks are recorded in the recent period; verify whether this target is already inactive.'
    elif target.get('recent_click_share') is not None and target['recent']['clicks']:
        reason += f" It supplies {target['recent_click_share']:.1%} of recent paid clicks; monitor exposure and total company sales during any test."
    return dict(result,available=True,result=verdict,action=action,reason=reason,
                cpc=cpc,ceiling_low=max(0,lower),ceiling_high=max(0,upper),
                uncertainty_low=uncertain_low,uncertainty_high=uncertain_high,
                contribution_per_click_low=lower-cpc,contribution_per_click_high=upper-cpc,
                recent_reference=reference is target['recent'],economics=economics,
                scope='Estimated direct paid contribution, not incremental company profit; assumes future order value and conversion resemble the fitted history. Purchased ASIN mix is not linked, so the margin band is a scenario, not a guaranteed bound. Refunds, fixed overhead and unmeasured sales spillovers are excluded.')
