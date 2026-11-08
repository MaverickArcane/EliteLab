"""Isolated real UI/API with synthetic cargo, markets, carrier and journal events."""
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from test_ptn import PTNTests
from test_selling import SellingTests
from elitelab.core.http import make_handler

fixture=PTNTests();fixture.setUp();core=fixture.core
markets=SellingTests();markets.clock=datetime.now(timezone.utc)
records=[markets.market(1,10,100,50,5,10),markets.market(2,30,90,80,10,20)]
fetch=core.services.fetch_json
def provider(url,*args,**kwargs):
    if '/api/stations/search' in url:
        return dict(results=records,count=len(records))
    return fetch(url,*args,**kwargs)
core.services.fetch_json=provider
core.bus.emit('journal.Loadout',dict(event='Loadout',timestamp=datetime.now(timezone.utc).isoformat(),
    Ship='python',ShipID=42,ShipName='Release test ship',HullHealth=.95,Modules=[
        dict(Slot='FrameShiftDrive',Item='int_hyperdrive_size5_class5',Health=.7,On=True),
        dict(Slot='Slot01_Size6',Item='int_cargorack_size6_class1',Health=1,On=False)]))
core.bus.emit('journal.file.Status',dict(Flags=(1<<24)|8,Fuel=dict(FuelMain=20)))
core.store.update('journal',dict(cmdr='Release Test Commander',system='Sol',star_pos=[0,0,0],
    cargo_capacity=100,shields_up=True,hull_health=.95,
    cargo=dict(count=30,items=[dict(key='gold',name='Gold',count=10,stolen=0),dict(key='silver',name='Silver',count=20,stolen=0)])))
core.modules['trade'].trade.data['carrier_id']=123

def sale(q):
    event=dict(event='MarketSell',timestamp=datetime.now(timezone.utc).isoformat(),MarketID=1,Type='gold',Count=3,TotalSale=300)
    core.bus.emit('journal.MarketSell',event);core.bus.emit('journal.MarketSell',event)
    core.store.set('journal','cargo',dict(count=27,items=[dict(key='gold',name='Gold',count=7,stolen=0),dict(key='silver',name='Silver',count=20,stolen=0)]))
    return core.store.get('selling')

core.http.route('/audit/selling/sale',sale,method='POST')

def mining_buyer(q):
    timestamp=datetime.now(timezone.utc).isoformat()
    core.bus.emit('journal.Docked',dict(event='Docked',timestamp=timestamp,StationName='Buyer',StarSystem='Lave',StationType='Orbis',MarketID=456))
    core.bus.emit('journal.file.Market',dict(timestamp=datetime.now(timezone.utc).isoformat(),MarketID=456,
        StationName='Buyer',StarSystem='Lave',Items=[dict(Name='$platinum_name;',Name_Localised='Platinum',
        BuyPrice=0,SellPrice=280000,Stock=0,Demand=1000,MeanPrice=57000,Consumer=True)]))
    fixture.carrier(system='Lave',stats_time=fixture.time())
    return core.store.get('ptn')

core.http.route('/audit/mining/buyer',mining_buyer,method='POST')
server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(core))
print(server.server_port,flush=True)
try:
    server.serve_forever()
finally:
    server.server_close();fixture.doCleanups()
