"""Real CLI with only synthetic community station responses for browser tests."""
import datetime as dt
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from elitelab.core import config
from elitelab.core.services import Services
from elitelab.__main__ import main

config.OFFLINE = False


def fetch(self, url, body=None, **kwargs):
    if url not in ('https://spansh.co.uk/api/stations/search','https://www.spansh.co.uk/api/stations/search'):
        raise ValueError('Browser fixture blocks unrelated network requests')
    ref=(body or {}).get('reference_system')
    if ref=='Unavailable test':
        raise ValueError('Synthetic provider unavailable')
    if ref=='Empty test' or float((body or {})['filters'].get('distance',{}).get('min',0))>=400:
        return {'count':0,'results':[]}
    power=(body or {})['filters'].get('system_power',{}).get('value',['Edmund Mahon'])[0]
    return {'count':1,'results':[{'market_id':500,'name':'Fixture Exchange','system_name':'Fixture Target',
        'system_power':power,'system_power_state':'Unoccupied','type':'Coriolis Starport','has_market':True,
        'has_large_pad':True,'distance':150,'distance_to_arrival':200,'system_population':5000000,
        'system_x':150,'system_y':0,'system_z':0,'market_updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'market':[{'commodity':'Leathery Eggs','sell_price':25000,'demand':1000,'supply':0}]}]}


Services.fetch_json=fetch
raise SystemExit(main(['serve','--no-browser']))
