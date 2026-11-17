"""Read-only HUD adapters. They consume existing local API results, never run searches."""
from datetime import datetime, timezone
from functools import wraps

from .hud_model import Card, Mode, finite, number as n


def connected(builder):
    @wraps(builder)
    def view(state, online=True):
        if not online:
            return Card(title='EliteLab HUD', status='OFFLINE', primary='Connection lost',
                        note='Reconnecting. Readouts paused.', visual=badge('LINK'))
        return builder(state)
    return view


def badge(label, text='--'):
    return {'kind': 'badge', 'label': label, 'text': str(text)}


def gauge(value, label):
    return {'kind': 'gauge', 'value': value if finite(value) else None, 'label': label}


def percent(have, total):
    return max(0, min(100, 100 * have / total)) if finite(have) and finite(total) and total > 0 else None


def money(value):
    if not finite(value):
        return '--'
    for divisor, unit in ((1e9, 'B'), (1e6, 'M'), (1e3, 'k')):
        if abs(value) >= divisor:
            return f'{value/divisor:.2f}{unit} Cr'
    return n(value, ' Cr')


def words(value):
    return str(value or '').replace('_', ' ').strip()


def fresh(timestamp, limit=120):
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace('Z', '+00:00'))).total_seconds()
        return -5 <= age <= limit
    except (ValueError, TypeError, AttributeError):
        return False


def empty(title, instruction):
    return Card(title=title, primary='Nothing selected', note=instruction)


def telemetry(s):
    status = s.get('status') or {}
    live = s.get('game_running') is not False and fresh(status.get('timestamp'))
    return status if live else {}, live


@connected
def overview(s):
    status, live = telemetry(s)
    fuel = status.get('fuel') if fresh(status.get('fuel_at')) else None
    warnings = [label for key, label in (('low_fuel', 'LOW FUEL'), ('overheating', 'OVERHEATING'),
                ('in_danger', 'IN DANGER'), ('interdicted', 'INTERDICTED')) if status.get(key)]
    activity = 'Docked' if status.get('docked_flag') else 'Landed' if status.get('landed') else 'Supercruise' if status.get('supercruise') else 'In flight'
    return Card(title=(s.get('ship_name') or '').strip() or s.get('ship') or 'Commander', context=s.get('system') or 'Location unknown',
                status='LIVE TELEMETRY' if live else 'LAST OBSERVATION', primary=warnings[0] if warnings else activity if live else 'Telemetry paused',
                secondary=s.get('station') or status.get('body') or '', metric=n(fuel, ' t'), metric_label='FUEL / LAST REPORT',
                stats=(('CREDITS', money(s.get('credits'))), ('SHIP JUMP RANGE', n(s.get('jump_range_now'), ' ly'))),
                note='Live flags need a recent game Status report.', warning=' / '.join(warnings),
                tone='green' if live and not warnings else 'amber', visual=badge('SHIP', str(status.get('vehicle') or '--').upper()))


@connected
def flight(s):
    status = s.get('status') or 'unknown'
    valid = status == 'plotted'
    arrival = status == 'arrived'
    return Card(title='Plotted ship route', context=(s.get('current_location') or {}).get('system') or '',
                status=words(status).upper(), primary=(s.get('next_system') or 'Next system unknown') if valid else 'Destination reached' if arrival else 'Plot a route in game',
                primary_label='NEXT SYSTEM' if valid else '', secondary=('To ' + s['destination']) if s.get('destination') else '',
                metric=n(s.get('remaining_jumps') if valid or arrival else None), metric_label='JUMPS REMAINING',
                stats=(('ROUTE DISTANCE', n(s.get('remaining_distance_ly') if valid or arrival else None, ' ly')),
                       ('NEXT STAR', str((s.get('remaining_route') or [{}])[0].get('star_class') or '--') if valid else '--')),
                note='Last plotted route. Check fuel and the in-game route.',
                warning='Position is not established on this route.' if status in ('off_route', 'ambiguous_position') else '',
                tone='green' if arrival else 'amber', visual=badge('JUMPS', n(s.get('remaining_jumps') if valid or arrival else None)))


@connected
def cargo(s):
    hold = s.get('cargo') or {}
    count, capacity = hold.get('count'), s.get('cargo_capacity')
    rows = sorted(hold.get('items') or [], key=lambda r: -(r.get('count') or 0))
    free = max(0, capacity-count) if finite(count) and finite(capacity) else None
    return Card(title='Cargo hold', context=s.get('ship') or '', status='LAST CARGO REPORT',
                primary=n(count, ' t'), primary_label='ABOARD', secondary=rows[0].get('name', '') if rows else 'No goods reported' if count == 0 else '',
                metric=n(free, ' t'), metric_label='SPACE FREE',
                stats=(('CAPACITY', n(capacity, ' t')), ('COMMODITIES', n(len(rows)) if hold else '--')),
                note='Reported inventory; mission and stolen cargo may need special handling.', visual=gauge(percent(count, capacity), 'HOLD'))


@connected
def market(s):
    report = s.get('market') or {}
    current = bool(s.get('docked') and s.get('station') == report.get('station') and s.get('system') == report.get('system'))
    rares = report.get('rares_in_stock') or []
    return Card(title='Local market', context=report.get('system') or '', status='CURRENT STATION REPORT' if current else 'PREVIOUS STATION REPORT',
                primary=report.get('station') or 'Open a market in game', primary_label='REPORTED MARKET',
                secondary=report.get('timestamp') or '', metric=n(len(report.get('commodities') or [])) if report else '--',
                metric_label='COMMODITIES REPORTED', stats=(('RARES IN STOCK', n(len(rares)) if report else '--'),
                ('RARE TONNES', n(sum(r.get('stock') or 0 for r in rares), ' t') if report else '--')),
                note='Prices and availability are observations.', warning='' if current else 'Open the market at your current station to refresh.', visual=badge('MARKET'))


@connected
def combat(s):
    status, live = telemetry(s)
    shield = status.get('shields_up')
    hull = s.get('hull_health')
    hull = hull * 100 if finite(hull) else None
    return Card(title='Combat telemetry', context=s.get('system') or '', status='LIVE STATUS' if live else 'TELEMETRY PAUSED',
                primary='Shields up' if shield is True else 'Shields down' if shield is False else 'Status unavailable',
                secondary='Hardpoints deployed' if status.get('hardpoints') else '',
                metric=n(hull, '%'), metric_label='HULL / LAST REPORTED',
                stats=(('FUEL', n(status.get('fuel') if fresh(status.get('fuel_at')) else None, ' t')),
                       ('LEGAL STATUS', words(status.get('legal')) or '--')),
                warning='OVERHEATING' if status.get('overheating') else 'IN DANGER' if status.get('in_danger') else '',
                note='Shield flags are live; hull is the last damage/loadout report.',
                tone='green' if shield is True else 'amber', visual=gauge(hull, 'HULL'))


@connected
def powerplay(s):
    return Card(title=s.get('power') or 'Not pledged', status='RECORDED MERITS', primary=n(s.get('session_merits')),
                primary_label='GAINED THIS SESSION', metric=n(s.get('merits')), metric_label='TOTAL MERITS',
                stats=(('RANK', n(s.get('rank'))), ('CYCLE HOURS LEFT', n(round(s['cycle_hours_left'], 1) if finite(s.get('cycle_hours_left')) else None))),
                note='Recorded gains, not projected rewards.', visual=badge('POWER', n(s.get('rank'))))


@connected
def merits(s):
    return Card(title='Merit pace', status='SESSION AVERAGE', primary=n(s.get('per_hour'), ' /h'), primary_label='MERITS PER HOUR',
                secondary='Last hour: ' + n(s.get('last_hour')), metric=n(s.get('session_merits')), metric_label='GAINED THIS SESSION',
                stats=(('EARNING PACE', n(s.get('per_hour_earning'), ' /h')), ('UNATTRIBUTED', n(s.get('unattributed')))),
                note='Activity associations are estimates; gains are recorded.', visual=badge('MERITS'))


@connected
def loop(s):
    stop, workflow = s.get('next') or {}, s.get('workflow') or {}
    done, total = s.get('done_count'), len(s.get('stations') or [])
    return Card(title=s.get('name') or 'Rare goods loop', status='SWEEP COMPLETE' if s.get('complete') else 'NEXT BUY STOP',
                primary=stop.get('station') or 'Sweep complete' if s.get('complete') else stop.get('station') or 'Choose a loop',
                secondary=stop.get('system') or '', metric=n(s.get('tons_total'), ' t'), metric_label='LOOP GOODS ABOARD',
                stats=(('STOPS SWEPT', n(done) + '/' + n(total)), ('SPACE FREE', n(workflow.get('free_capacity'), ' t'))),
                note='Next stop: ' + n(stop.get('dist'), ' ly') if stop else 'Choose a selling destination in EliteLab.',
                visual=gauge(percent(done, total), 'STOPS'))


@connected
def personal(s):
    progress, plan = s.get('progress') or {}, s.get('plan') or {}
    if not plan:
        return empty('Trading', 'Select a trade route in the Trading panel.')
    stop = progress.get('next') or {}
    return Card(title='Trading / ' + words(progress.get('stage')), context=stop.get('system') or '', status='SELECTED ROUTE',
                primary=progress.get('title') or 'Check route', secondary=stop.get('station') or '',
                metric=n(progress.get('quantity'), ' t'), metric_label='NEXT ACTION QUANTITY',
                stats=(('LEG', n(progress['leg'] + 1 if finite(progress.get('leg')) else None) + '/' + n(progress.get('leg_count'))), ('EST. ROUTE PROFIT', money(plan.get('profit')))),
                note=progress.get('reason') or '', warning='Commander changed. Select a route again.' if progress.get('commander_changed') else '',
                visual=badge('TRADE', words(progress.get('action')).upper()[:8]))


@connected
def selling(s):
    plan = s.get('plan') or {}
    if not plan:
        return empty('Sell cargo', 'Select a sale plan in the Sell cargo panel.')
    stop = plan.get('next_stop') or {}
    remaining = sum(r.get('remaining') or 0 for r in stop.get('sales', []))
    return Card(title='Cargo sale plan', context=stop.get('system') or '', status='COMPLETE' if plan.get('complete') else 'NEXT SALE',
                primary='Sales complete' if plan.get('complete') else stop.get('station') or 'Check sale plan',
                metric=n(remaining, ' t') if stop or plan.get('complete') else '--', metric_label='TO SELL AT THIS STOP',
                stats=(('STOPS IN PLAN', n(len(plan.get('stops') or []))), ('QUOTE STATUS', 'Stale' if plan.get('quotes_stale') else 'Reported')),
                warning='Cargo changed; review the sale plan.' if plan.get('cargo_changed') else 'Quotes are old; check prices and demand.' if plan.get('quotes_stale') else '',
                note='Planned sales are not completed sale receipts.', visual=badge('SELL'))


@connected
def hauling(s):
    desk = s.get('desk') or {}
    if not desk:
        return empty('My hauling run', 'Select a carrier job or join a hauling party.')
    action = desk.get('action')
    labels = {'buy': 'Pick up cargo', 'deliver': 'Deliver cargo', 'transfer_in': 'Transfer to carrier',
              'transfer_out': 'Collect from carrier', 'wait': 'Wait for next run', 'travel': 'Travel to stop'}
    stop = desk.get('delivery' if action in ('deliver', 'transfer_in') else 'pickup') or {}
    paused = desk.get('stale') or desk.get('paused') or s.get('stale')
    return Card(title=desk.get('commodity') or 'My hauling run', context=stop.get('system') or '',
                status='PAUSED' if paused else words(desk.get('phase')).upper(), primary='Check crew connection' if paused else labels.get(action, words(action) or 'Check job'),
                secondary=stop.get('station') or '', metric='--' if paused else n(desk.get('quantity'), ' t'), metric_label='NEXT LOAD / DELIVERY',
                stats=(('COMMODITY ABOARD', n(desk.get('aboard'), ' t')), ('HOLD CAPACITY', n(desk.get('capacity'), ' t'))),
                note=desk.get('reason') or 'Suggested loads are shared estimates.', visual=gauge(percent(desk.get('cargo_count'), desk.get('capacity')), 'HOLD'))


@connected
def trade(s):
    plan, calc = s.get('plan') or {}, s.get('calculation') or {}
    if not plan:
        return empty('Carrier job', 'Choose a carrier operation in EliteLab.')
    return Card(title=words(plan.get('commodity')) or 'Carrier job', context=plan.get('destination') or plan.get('source') or '',
                status=words((s.get('operation') or {}).get('stage') or plan.get('mode')).upper(), primary=n(calc.get('remaining'), ' t'),
                primary_label='REMAINING TO TARGET', secondary='Carrier stock: ' + n(calc.get('stock'), ' t'),
                metric=n(calc.get('next_load'), ' t'), metric_label='ESTIMATED NEXT LOAD',
                stats=(('EST. RUNS LEFT', n(calc.get('runs'))), ('TARGET STOCK', n(plan.get('target'), ' t'))),
                note='Stock and orders are separate. Check the current job stage.', visual=badge('RUNS', n(calc.get('runs'))))


@connected
def ptn(s):
    op, plan = s.get('operation') or {}, s.get('plan') or {}
    if not plan:
        return empty('PTN trade desk', 'Select a PTN operation in EliteLab.')
    phase = op.get('phase') or plan.get('stage')
    stop = op.get('buy' if phase == 'loading' else 'sell') or {}
    blockers = op.get('blockers') or []
    return Card(title=plan.get('name') or words(plan.get('commodity')) or 'PTN operation', context=stop.get('system') or '',
                status=words(phase).upper(), primary=n(op.get('remaining'), ' t'), primary_label='REPORTED ORDER REMAINING',
                secondary=stop.get('station') or '', metric=money((op.get('pricing') or {}).get('loading_per_ton' if phase == 'loading' else 'unloading_per_ton')),
                metric_label='PLANNED HAULER PAY / TONNE', stats=(('READINESS', 'Check required' if blockers else 'Ready' if op.get('ready') else 'Not ready'),
                ('EST. RUNS', n(op.get('runs')))), warning=blockers[0] if blockers else '',
                note=op.get('remaining_source') or 'Check current order, docking and prices in game.', visual=badge('PTN'))


@connected
def carrier(s):
    followed = (s.get('carrier') or {}).get('pinned') or {}
    owned = (s.get('journal') or {}).get('carrier') or {}
    c = followed or owned
    if not c:
        return empty('Fleet carrier', 'Follow a carrier or receive an owned-carrier report.')
    return Card(title=c.get('name') or c.get('callsign') or 'Fleet carrier', context=c.get('callsign') or '',
                status='FOLLOWED / LAST REPORT' if followed else 'OWNED / LAST REPORT', primary=c.get('system') or 'System unknown',
                secondary=c.get('observed_at') or c.get('stats_time') or '', metric=n(c.get('distance'), ' ly') if followed else n(c.get('fuel'), ' t'),
                metric_label='REPORTED DISTANCE' if followed else 'TRITIUM RESERVE',
                stats=(('DOCKING', words(c.get('docking')) or '--'), ('SPACE FREE', n(c.get('free_space'), ' t'))),
                note='Carrier location and stocks are last reported observations.', visual=badge('CARRIER'))


@connected
def materials(s):
    session = s.get('session') or {}
    gain, totals = session.get('last_gain') or {}, session.get('totals') or {}
    return Card(title='Material collection', context=words(gain.get('name')), status='THIS GAME SESSION', primary=n(session.get('gained')),
                primary_label='UNITS GAINED', secondary=('Last receipt: +' + n(gain.get('count'))) if gain else '',
                metric=n(totals.get('Raw')), metric_label='RAW GAINED',
                stats=(('MANUFACTURED GAINED', n(totals.get('Manufactured'))), ('ENCODED GAINED', n(totals.get('Encoded')))),
                note='Includes pickups, mission rewards and trader receipts.', visual=badge('MATS', '+' + n(gain.get('count')) if gain else '--'))


@connected
def wishlist(s):
    s = s.get('wishlist') or {}
    summary = s.get('summary') or {}
    needs = s.get('needs') or []
    known = s.get('inventory_known') is True
    required = sum(r.get('need') or 0 for r in needs)
    missing = summary.get('units_short') if known else None
    have = required - missing if finite(missing) else None
    return Card(title='Materials / recipe wishlist', status='MATERIAL BUDGET' if known else 'INVENTORY UNKNOWN',
                primary=n(missing), primary_label='UNITS STILL NEEDED', secondary=n(summary.get('entries'), ' planned entries'),
                metric=n(summary.get('short') if known else None), metric_label='MATERIAL TYPES SHORT',
                stats=(('REQUIRED UNITS', n(required) if needs else '--'), ('MATERIALS COVERED', 'Yes' if known and summary.get('complete') else 'No' if known else '--')),
                note='Material coverage does not mean the upgrades are installed.', visual=gauge(percent(have, required), 'BUDGET'))


@connected
def build(s):
    p, target = s.get('progress') or {}, s.get('pinned') or {}
    if not target:
        return empty('Ship build', 'Pin a target build in the Ship build panel.')
    totals = p.get('totals') or {}
    same = p.get('same_ship') is True
    return Card(title=target.get('name') or 'Pinned build', context=p.get('target_ship') or target.get('ship') or '',
                status='CURRENT SHIP' if same else 'DIFFERENT SHIP', primary=n((p.get('percent') or {}).get('overall'), '%') if same else 'Switch to target ship',
                primary_label='UPGRADES COMPLETE' if same else '', metric=n(totals.get('to_engineer')) if same else '--', metric_label='MODULES TO ENGINEER',
                stats=(('MODULES TO BUY', n(totals.get('to_buy')) if same else '--'), ('MATERIAL TYPES SHORT', n(p.get('materials_short')))),
                note='Materials and installed upgrades are separate.', warning='Completion needs an updated loadout.' if same and not p.get('completion_known') else '',
                visual=gauge((p.get('percent') or {}).get('overall') if same else None, 'BUILD'))


@connected
def engineers(s):
    rows = s.get('engineers') or []
    unlocked = [r for r in rows if (r.get('access') or {}).get('unlocked') is True]
    invited = [r for r in rows if (r.get('access') or {}).get('progress') == 'Invited']
    return Card(title='Engineer access', status='REVIEWED CATALOG', primary=n(len(unlocked)) + '/' + n(len(rows)), primary_label='UNLOCKED / REVIEWED',
                secondary='First invitation: ' + str(invited[0].get('engineer')) if invited else 'Review engineer steps in EliteLab',
                metric=n(len(invited)), metric_label='RECORDED INVITATIONS',
                stats=(('REVIEWED ENGINEERS', n(len(rows))), ('UNKNOWN ACCESS', n(sum(not r.get('access') or (r['access'].get('progress') == 'unknown') for r in rows)))),
                note='Reviewed catalog only; missing access remains unknown.', visual=gauge(percent(len(unlocked), len(rows)), 'ACCESS'))


@connected
def synthesis(s):
    boosts = {r.get('grade'): r.get('craftable') for r in s.get('injections') or []}
    boost = s.get('boost') or {}
    return Card(title='FSD synthesis', status='LAST BOOST OBSERVATION', primary=words(boost.get('status')) or 'Boost unknown',
                secondary=boost.get('observed_at') or '', metric=n(boosts.get('premium')), metric_label='PREMIUM CRAFTABLE',
                stats=(('BASIC CRAFTABLE', n(boosts.get('basic'))), ('STANDARD CRAFTABLE', n(boosts.get('standard')))),
                note='Each recipe count uses the same inventory, not reserved stock.', visual=badge('FSD'))


@connected
def missions(s):
    rows = s.get('missions') or []
    if not rows:
        return Card(title='Mission supplies', primary='No active missions', metric='0', metric_label='OBSERVED MISSIONS', note='Accept a mission in game to start tracking.')
    row = sorted(rows, key=lambda r: (r.get('expired') is True, r.get('expiry') or '9999', str(r.get('mission_id'))))[0]
    stop = row.get('hand_in') or {}
    return Card(title=row.get('localised_name') or words(row.get('name')) or 'Mission supplies', context=stop.get('system') or '',
                status='DEADLINE PASSED' if row.get('expired') else 'EARLIEST DEADLINE', primary=n(row.get('remaining_to_deliver'), ' t'),
                primary_label='REMAINING TO DELIVER', secondary=stop.get('station') or '', metric=n(row.get('aboard_allocated'), ' t'), metric_label='CARGO ALLOCATED',
                stats=(('SHORTFALL', n(row.get('shortfall'), ' t')), ('ACTIVE MISSIONS', n(len(rows)))),
                note=row.get('next_action') or '', warning='Cargo report needs refreshing.' if not s.get('cargo_current') else '',
                visual=badge('DUE', str(row.get('expiry') or '--')[11:16] or '--'))


@connected
def neutron(s):
    next_stop, route = s.get('next_waypoint') or {}, s.get('route') or {}
    if not route:
        return empty('Neutron highway', 'Plan a route in the Neutron highway panel.')
    changed = s.get('ship_changed') or s.get('fit_changed')
    return Card(title='Neutron highway', context=(s.get('location') or {}).get('system') or '', status=words(s.get('navigation_status')).upper(),
                primary='Check ship and replan' if changed else next_stop.get('system') or 'No next waypoint', primary_label='NEXT WAYPOINT' if next_stop and not changed else '',
                secondary=('To ' + str((route.get('request') or {}).get('to'))) if (route.get('request') or {}).get('to') else '',
                metric=n(s.get('remaining_waypoints')) if not changed else '--', metric_label='WAYPOINTS REMAINING',
                stats=(('NEXT LEG', n(next_stop.get('distance_from_previous_ly'), ' ly') if not changed else '--'),
                       ('UNBOOSTED RANGE', n((s.get('ship') or {}).get('suggested_range_ly'), ' ly'))),
                warning='Ship or fit changed; the saved route needs rechecking.' if changed else '',
                note='Waypoints can take several jumps. Refuelling is not planned.', visual=badge('ROUTE', n(s.get('remaining_waypoints')) if not changed else '--'))


@connected
def history(s):
    if s.get('selection_required'):
        return empty('Travel history', 'Choose a commander in EliteLab to view history.')
    return Card(title='Travel / last 24 hours', status='RECORDED TRAVEL', primary=n(s.get('total_ly'), ' ly'), primary_label='DISTANCE TRAVELLED',
                metric=n(s.get('jumps')), metric_label='RECORDED JUMPS',
                stats=(('SYSTEMS VISITED', n(len(s.get('systems') or []))), ('PERIOD', n(s.get('days'), ' day'))),
                note='Only available journal history is included.', visual=badge('JUMPS', n(s.get('jumps'))))


@connected
def feed(s):
    rows = s.get('feed') or []
    row = rows[0] if rows else {}
    return Card(title='Recent activity', context=s.get('system') or '', status='LAST JOURNAL EVENT',
                primary=words(row.get('event')) or 'Waiting for events', secondary=row.get('ts') or '',
                metric=money(s.get('credits')), metric_label='REPORTED CREDITS', note=row.get('text') or '', visual=badge('EVENT'))


@connected
def targets(s):
    last = (s.get('targets') or {}).get('last') or {}
    rows = last.get('results') or []
    if not rows:
        return empty('Powerplay buyers', 'Run a buyer search in EliteLab to see its first result.')
    row = rows[0]
    return Card(title='Powerplay buyers', context=row.get('system') or '', status='FIRST RESULT / LAST SEARCH',
                primary=row.get('station') or 'Station unknown', metric=n(row.get('dist'), ' ly'), metric_label='FROM SEARCH ORIGIN',
                stats=(('EST. JUMPS', n(row.get('jumps'))), ('RESULTS', n(len(rows)))),
                note='Search candidate; verify demand, access and merit eligibility.', visual=badge('BUYER'))


@connected
def profits(s):
    session, run = s.get('session') or {}, s.get('estimate') or {}
    last = (session.get('recent') or [{}])[0]
    value = session.get('profit')
    warning = 'Missing sale evidence; total unknown.' if session.get('unknown_sales') else 'Partial journal session.' if session.get('partial') else ''
    return Card(title='Trading profit', context=run.get('commodity') or last.get('commodity') or '',
                status='SESSION ENDED' if session.get('ended') else 'RECORDED MARKET SALES',
                primary=money(value), primary_label='EARNED THIS SESSION',
                secondary=n(session.get('sold_tons'), ' t sold'),
                metric=money(run.get('profit')), metric_label=(run.get('label') or 'CURRENT RUN ESTIMATE').upper(),
                stats=(('LATEST SALE PROFIT', money(last.get('profit'))), ('SALES', n(session.get('sales')))),
                note='Before fuel, repairs, fees and crew. ' + (run.get('note') or 'Select a route or hauling job for an estimate.'),
                warning=warning or run.get('warning') or '', tone='green' if finite(value) and value >= 0 else 'amber', visual=badge('PROFIT', 'Cr'))


# Endpoint choices deliberately exclude discovery, search, join, posting and planning operations.
PROVIDERS = {
    'overview': ('/api/journal', 'status', overview, 1),
    'flight': ('/api/flight/navigation?limit=1', 'status', flight, 1),
    'cargo': ('/api/journal', 'cargo', cargo, 1),
    'market': ('/api/journal', 'market', market, 3),
    'combat': ('/api/journal', 'status', combat, 1),
    'powerplay': ('/api/powerplay', 'power', powerplay, 2),
    'merits': ('/api/merits', 'session_merits', merits, 3),
    'loop': ('/api/loop', 'stations', loop, 1),
    'personal': ('/api/personal/plan', 'plan', personal, 1),
    'profits': ('/api/profits', 'session', profits, 1),
    'selling': ('/api/selling', 'plan', selling, 2),
    'hauling': ('/api/party', 'mode', hauling, 1),
    'trade': ('/api/trade', 'plan', trade, 2),
    'ptn': ('/api/ptn', 'plan', ptn, 3),
    'carrier': ('/api/state', 'journal', carrier, 3),
    'materials': ('/api/materials', 'session', materials, 1),
    'wishlist': ('/api/state', 'wishlist', wishlist, 3),
    'build': ('/api/build', 'pinned', build, 3),
    'engineers': ('/api/progression/catalog', 'engineers', engineers, 5),
    'synthesis': ('/api/synthesis/status', 'boost', synthesis, 2),
    'missions': ('/api/missions/plan', 'missions', missions, 2),
    'neutron': ('/api/neutron/route?limit=1', 'navigation_status', neutron, 2),
    'history': ('/api/history?days=1', 'jumps', history, 10),
    'feed': ('/api/journal', 'feed', feed, 2),
    'targets': ('/api/state', 'targets', targets, 3),
}
