"""Encode real browser captures; Pillow is only an optional documentation tool.

Set ELITELAB_GIF_FRAMES to a temporary directory and run
node tests/material-plan-browser.mjs, then pass that directory to this script.
Use a separate virtual environment with Pillow; the app has no dependencies.
"""
import argparse
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('frames',type=Path)
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs'/'gifs')
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
for name in ('materials-recipes','materials-exchanges','materials-progress'):
    paths=sorted((args.frames/name).glob('*.png'))
    if len(paths)<2:
        raise ValueError(f'Missing browser frames for {name}')
    frames=[]
    for path in paths:
        with Image.open(path) as source:
            frame=source.convert('RGB');frame.thumbnail((1100,800))
            frames.append(frame.quantize(colors=128))
    target=args.output/(name+'.gif')
    frames[0].save(target,save_all=True,append_images=frames[1:],duration=2200,loop=0,optimize=True)
    print(f'{target}: {len(frames)} real UI frames, {target.stat().st_size} bytes')
