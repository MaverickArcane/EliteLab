"""Commodity margins, not credit balance changes or assumed crew payments.

Frontier Player Journal v37 section 7.6 documents MarketSell.TotalSale and
AvgPricePaid. Profit here is the sale receipt less Count * AvgPricePaid;
fuel, repairs, fees and NPC crew deductions are outside this measure.
https://hosting.zaonce.net/community/journal/v37/Journal_Manual_v37.pdf
"""
import math
import threading


def number(value, maximum=10**15):
    return value if type(value) in (int, float) and 0 <= value <= maximum and math.isfinite(value) else None


def text(value):
    return value.strip()[:160] if isinstance(value, str) else ''


def estimate(personal, party, commander):
    """Read existing plans; never turn planned prices or deliveries into receipts."""
    if not commander:
        return None
    desk = party.get('desk') or {}
    if desk.get('operation_id') and desk.get('phase') not in ('complete', 'cancelled'):
        paused = party.get('stale') or desk.get('stale') or desk.get('paused')
        value = desk.get('load_earnings')
        if paused or desk.get('owner') or desk.get('action') not in ('buy', 'deliver'):
            value = None
        return {'source': 'hauling', 'label': 'Hauling run estimate',
                'profit': value, 'commodity': desk.get('commodity'),
                'quantity': desk.get('quantity'), 'per_ton': desk.get('per_ton'),
                'note': 'Run paused; estimate unavailable.' if paused else 'At agreed job prices; not a payment receipt.'}
    plan, progress = personal.get('plan') or {}, personal.get('progress') or {}
    index = progress.get('leg')
    if (not plan.get('cmdr') or plan['cmdr'] != commander
            or progress.get('commander_changed') or type(index) is not int
            or not 0 <= index < len(plan.get('legs') or [])):
        return None
    leg = plan['legs'][index]
    buying = progress.get('stage') in ('buy', 'travel_buy')
    # A buy action can be a top-up. Estimate the planned leg, not just the top-up.
    quantity = number(leg.get('quantity') if buying else progress.get('quantity'), 1000000)
    buy, sell = number((leg.get('buy') or {}).get('price')), number((leg.get('sell') or {}).get('price'))
    spread = sell - buy if buy is not None and sell is not None else None
    quote = progress.get('quotes') or {}
    return {'source': 'route', 'label': 'Current leg estimate', 'commodity': leg.get('commodity'),
            'quantity': quantity, 'per_ton': spread,
            'profit': quantity * spread if quantity is not None and spread is not None else None,
            'warning': text(quote.get('message')) if quote.get('status') != 'fresh' else '',
            'note': 'At selected route prices; actual purchase and sale prices may differ. ' + text(quote.get('message'))}


class Profits:
    def __init__(self, core):
        self.core, self.lock = core, threading.RLock()
        self.reset()
        core.bus.on('journal.*', self.event)
        core.bus.on('journal.replay.done', lambda n, v: self.publish())
        for signal in ('state.personal.plan', 'state.personal.progress', 'state.party.desk', 'state.party.stale'):
            core.bus.on(signal, lambda n, v: self.publish())
        self.publish()

    def reset(self, commander='', fid='', started=None, partial=True):
        self.commander, self.fid = commander, fid
        self.started, self.partial, self.ended = started, partial, False
        self.known_profit = self.proceeds = self.tons = self.sales = 0
        self.unknown_sales = self.unknown_proceeds = self.unknown_quantity = 0
        self.recent = []

    def event(self, name, ev):
        if not isinstance(ev, dict):
            return
        event = ev.get('event')
        with self.lock:
            if event in ('LoadGame', 'Commander'):
                commander, fid = text(ev.get('Commander') or ev.get('Name')), text(ev.get('FID'))
                if (event == 'LoadGame' or (fid and self.fid and fid != self.fid)
                        or (commander and self.commander and commander != self.commander)):
                    self.reset(commander, fid, text(ev.get('timestamp')) or None, event != 'LoadGame')
                else:
                    self.commander, self.fid = commander or self.commander, fid or self.fid
            elif self.ended:
                return
            elif event == 'Shutdown':
                self.ended = True
            elif event == 'MarketSell':
                quantity = number(ev.get('Count'), 1000000)
                total, paid = number(ev.get('TotalSale')), number(ev.get('AvgPricePaid'))
                if quantity is None or quantity == 0 or quantity != int(quantity):
                    # Even a malformed sale makes the session total incomplete.
                    quantity = None
                if total is None and quantity is not None and number(ev.get('SellPrice')) is not None:
                    total = number(ev['SellPrice'] * quantity)
                cost = number(paid * quantity) if paid is not None and quantity is not None else None
                profit = total - cost if total is not None and cost is not None else None
                self.sales += 1
                self.tons += quantity or 0
                self.unknown_quantity += int(quantity is None)
                self.proceeds += total or 0
                self.unknown_proceeds += int(total is None)
                self.unknown_sales += int(profit is None)
                self.known_profit += profit or 0
                self.recent.insert(0, {'at': text(ev.get('timestamp')), 'commodity': text(ev.get('Type_Localised') or ev.get('Type')),
                                       'quantity': quantity, 'proceeds': total, 'cost': cost, 'profit': profit})
                del self.recent[10:]
            else:
                return
            if not ev.get('_replay'):
                self.publish()

    def publish(self):
        with self.lock:
            session = {'commander': self.commander, 'started_at': self.started,
                       'partial': self.partial, 'ended': self.ended, 'sales': self.sales,
                       'sold_tons': None if self.unknown_quantity else self.tons,
                       'profit': None if self.unknown_sales else self.known_profit,
                       'known_profit': self.known_profit, 'unknown_sales': self.unknown_sales,
                       'proceeds': None if self.unknown_proceeds else self.proceeds,
                       'recent': list(self.recent)}
            party = {key: self.core.store.get('party', key) for key in ('desk', 'stale')}
            run = None if self.ended else estimate(self.core.store.get('personal'), party, self.commander)
            self.core.store.update('profits', {'session': session, 'estimate': run})


def setup(core, module):
    module.profits = Profits(core)
    core.http.route('/api/profits', lambda q: core.store.get('profits'), tool='get_trading_profits', module=module.name,
        description='Commodity sale profit for the latest game session: MarketSell.TotalSale less Count * AvgPricePaid, before fuel, repairs, fees and NPC crew deductions. Includes all commodity market sales, including mined goods with recorded zero purchase cost. Missing receipt or acquisition cost makes session.profit null; known_profit is only the known subtotal and unknown_sales counts incomplete receipts. recent contains the last ten sales. LoadGame or commander change resets; partial means no session start was seen. Unsold purchases, transfers, mission rewards and balance changes are not earnings. estimate is separately calculated from the active crew run (at agreed prices) or selected personal route leg (at quoted prices), never an actual receipt. Shutdown hides the run estimate.')
