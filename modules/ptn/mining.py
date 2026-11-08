"""Checked mined stock to public unloading, without invented purchase evidence."""
import copy
import math
import secrets
from datetime import datetime, timezone

from modules.ptn.planning import DEFAULTS, integer, key, line, now, stamp, station_kind, unlimited_demand

CHECKS = ('near_station', 'docking_open', 'funds_checked', 'competition_checked')


def handoff(desk, q):
    """Caller holds the PTN lock; read the source job's atomic public snapshot."""
    desk.guard(q, switching=True)
    old = desk.data.get('plan')
    if old and old['stage'] not in ('complete', 'cancelled'):
        raise ValueError('Finish or cancel the current PTN plan before importing a mined load.')
    job = desk.core.store.get('trade', 'job') or {}
    plan, op = job.get('plan') or {}, job.get('operation') or {}
    if (plan.get('activity') != 'mining' or op.get('id') != q.get('operation_id')
            or not op.get('id') or op.get('updated_at') != q.get('operation_updated_at')):
        raise ValueError('The mining job changed. Refresh Carrier ops before handing it to PTN.')
    if op.get('stage') not in ('transit', 'unloading') or op.get('paused'):
        raise ValueError('Finish loading and depart the unpaused mining job before preparing PTN unloading.')
    c = desk.context()
    if (not c['commander'] or not c['callsign'] or not c['carrier'] or not c['carrier_id']
            or plan.get('carrier_market_id') != c['carrier_id']):
        raise ValueError('Refresh the owned carrier identity; it must match the mining job.')
    quantity = integer(q.get('quantity'), 'Tonnes to advertise', 1, 25000)
    stock = integer(q.get('checked_stock'), 'Checked carrier stock', 0, 1000000)
    baseline = integer(op.get('baseline_stock'), 'Mining job baseline', 0, 1000000)
    if quantity > op['quantity'] or quantity > max(0, stock - baseline):
        raise ValueError('Advert tonnes must fit the checked stock above the saved baseline and the mining job size.')
    floor = integer(q.get('unloading_floor', 20000), 'Minimum unloading payout', 1, 1000000)
    j = desk.core.store.get('journal') or {}
    market = j.get('market') or {}
    buyer_id = integer(q.get('buyer_market_id'), 'Buyer market ID', 1, 10**16)
    raw = desk.latest_market
    clock = datetime.now(timezone.utc).timestamp()
    if (not j.get('docked') or station_kind(j.get('station_type')) != 'orbital'
            or j.get('station_type') == 'Outpost'
            or market.get('market_id') != buyer_id or raw.get('MarketID') != buyer_id
            or raw.get('timestamp') != market.get('timestamp')
            or raw.get('StarSystem') != j.get('system') or raw.get('StationName') != j.get('station')
            or not -300 <= clock - stamp(market.get('timestamp')) <= 900
            or stamp(market.get('timestamp')) < desk.docked_at):
        raise ValueError('Dock at a large-pad orbital buyer and open its current commodity market before handing off.')
    if plan.get('destination_market_id') and plan['destination_market_id'] != buyer_id:
        raise ValueError('This buyer is different from the saved mining job destination.')
    target = dict(market_id=buyer_id, station=line(j.get('station'), 'Buyer station'),
                  system=line(j.get('system'), 'Buyer system'), station_type=j['station_type'],
                  surface=False, price=None, volume=None, mean_price=None, arrival_ls=None,
                  body=None, observed_at=None, source='Buyer selected from current journal; capture still required')
    data = copy.deepcopy(desk.data)
    if old:
        data['history'] = ([dict(id=old['id'], commodity=old['name'], stage=old['stage'], ended_at=now())]
                           + data['history'])[:10]
    data['plan'] = dict(id=secrets.token_hex(12), kind='mining_unload', carrier=c['carrier'],
        callsign=c['callsign'], carrier_id=c['carrier_id'], commander=c['commander'],
        commodity=plan['commodity'], name=line(plan['commodity'].title(), 'Commodity'),
        route=dict(buy=None, sell=target, quantity=quantity,
                   settings={**DEFAULTS, 'haul_mode':'self_load', 'quantity':quantity,
                             'unloading_floor':floor, 'owner_floor':0, 'cost_reserve':0}),
        source=dict(operation_id=op['id'], operation_updated_at=op['updated_at'],
                    ring=plan['source'], checked_stock=stock, baseline_stock=baseline,
                    checked_at=now(), acquisition_cost=None),
        stage='scouting', created_at=now(), scouts={}, checks={}, orders={}, remaining={},
        remaining_at={}, posted={}, sco=True)
    # The source job remains independent: no cross-module call or lock is held.
    return desk.commit(data)


def operation(desk, plan):
    r, prefs, source = plan['route'], plan['route']['settings'], plan['source']
    sell = plan['scouts'].get('sell') or r['sell']
    c, clock = desk.context(), datetime.now(timezone.utc).timestamp()
    order = plan['orders'].get('unloading')
    remaining = plan['remaining'].get('unloading', r['quantity'])
    remaining_source, blockers = 'Owner-checked order', []
    journal_order = c['orders'].get(plan['commodity'], {})
    if order and stamp(journal_order.get('updated_at')) > max(stamp(order['checked_at']), stamp(plan.get('remaining_at', {}).get('unloading'))):
        if journal_order.get('side') != 'sell' or journal_order.get('price') != order['price']:
            blockers.append('A newer journal order has a different price or side. Recheck the actual sell order.')
        elif type(journal_order.get('quantity')) is int and 0 <= journal_order['quantity'] <= r['quantity']:
            remaining, remaining_source = journal_order['quantity'], 'Newer carrier order journal'
        else:
            blockers.append('The newer carrier sell order exceeds this plan size.')
    if (c['commander'] != plan['commander'] or c['callsign'] != plan['callsign']
            or c['carrier_id'] != plan['carrier_id']):
        blockers.append('The active commander or carrier does not match this mined load.')
    invalid = plan.get('invalid_scouts', {}).get('sell')
    if invalid:
        blockers.append(invalid['reason'] + ' Capture a valid buyer market and confirm the order again.')
    if 'sell' not in plan['scouts']:
        blockers.append('Capture the unloading station market; mined stock does not require a loading-station scout.')
    elif not -300 <= clock - stamp(sell.get('observed_at')) <= min(prefs['hours'] * 3600, 3600):
        blockers.append('The buyer scout has expired. Recheck its current market.')
    elif not unlimited_demand(sell, 'sell') and sell['volume'] < remaining:
        blockers.append('Buyer demand no longer covers the remaining order.')
    stock, stock_at, stock_source = source['checked_stock'], source['checked_at'], 'Owner-checked physical stock'
    ledger = c['inventory'].get(plan['commodity'], {})
    if stamp(ledger.get('updated_at')) > stamp(stock_at):
        stock, stock_at, stock_source = ledger.get('stock'), ledger.get('updated_at'), 'Newer carrier inventory evidence'
    if type(stock) is not int or stock < remaining + source['baseline_stock']:
        blockers.append('Checked carrier stock does not cover this order while preserving the mining job baseline.')
    if not -300 <= clock - stamp(stock_at) <= 3600:
        blockers.append('Recheck the physical carrier stock; its confirmation is over an hour old.')
    station_price, mean = sell.get('price'), sell.get('mean_price')
    percent = suggested = None
    if type(station_price) is int and type(mean) is int and mean > 0:
        options = [(p, (mean * p + 50) // 100) for p in range(5, 1001)]
        percent, suggested = next(((p, value) for p, value in reversed(options)
                                   if 0 < value <= station_price - prefs['unloading_floor']), (None, None))
    actual = order['price'] if order else suggested
    payout = station_price - actual if station_price is not None and actual is not None else None
    if station_price is not None and station_price <= prefs['unloading_floor']:
        blockers.append('The buyer price cannot support a positive carrier sell price and the minimum hauler payout.')
    basic = list(blockers)
    if plan['stage'] != 'unloading':
        blockers.append('Open the unloading phase before preparing its advert.')
    if key(c.get('system')) != key(sell['system']):
        blockers.append('The carrier is not reported in the buyer system.')
    if not -300 <= clock - stamp(c.get('stats_at')) <= 3600:
        blockers.append('Open Carrier Management to refresh carrier location and capacity.')
    checks = plan['checks'].get('unloading', {})
    labels = dict(near_station='Confirm the carrier is parked close to the station body.',
                  docking_open='Confirm docking access is open to haulers.',
                  funds_checked='Confirm the sell order and commodity market service are open.',
                  competition_checked='Check competing carriers and current buyer demand.')
    blockers.extend(labels[k] for k in CHECKS if checks.get(k) is not True)
    if not order:
        blockers.append('Enter and confirm the actual in-game carrier sell order price.')
    elif not -300 <= clock - stamp(order['checked_at']) <= 3600:
        blockers.append('Recheck the actual carrier sell order; its confirmation has expired.')
    elif payout is None or payout < prefs['unloading_floor']:
        blockers.append('The actual sell order underpays the minimum hauler payout.')
    if remaining <= 0:
        blockers.append('This order has no remaining tonnes to advertise.')
    costs = dict(station_buy=None, station_sell=station_price, mean_price=mean,
                 carrier_buy=None, carrier_sell=actual, buy_percent=None, sell_percent=percent,
                 loading_per_ton=None, unloading_per_ton=payout, owner_per_ton=None,
                 owner_total=None, owner_after_reserve=None, gross_total=None, cost_reserve=None,
                 hauler_total=None if payout is None else payout * r['quantity'],
                 carrier_proceeds=None if actual is None else actual * r['quantity'],
                 acquisition_cost=None, settings_valid=bool(payout is not None and payout >= prefs['unloading_floor']))
    posted = plan['posted'].get('unloading')
    return dict(revision=desk.data['revision'], plan_id=plan['id'], stage=plan['stage'],
                phase='unloading', public_phase=True, buy=None, sell=sell, pricing=costs,
                blockers=blockers, scout_blockers=basic, ready=not blockers, remaining=remaining,
                remaining_source=remaining_source, checks=checks, order=order, posted=posted,
                stock=dict(quantity=stock, observed_at=stock_at, source=stock_source),
                advert_expired=bool(posted and clock-stamp(posted['at']) >= 48*3600),
                runs=math.ceil(r['quantity']/prefs['hauler_capacity']),
                scenario_minutes=math.ceil(r['quantity']/prefs['hauler_capacity']/prefs['haulers'])*prefs['cycle_minutes'])
