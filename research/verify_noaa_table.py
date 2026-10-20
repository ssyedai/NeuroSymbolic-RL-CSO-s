"""Convert saved official NOAA AMS depth response without executing remote code."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import pandas as pd


def parse_response(text, html, javascript):
    values={}
    for line in text.splitlines():
        match=re.fullmatch(r'([A-Za-z_]+)\s*=\s*(.+);\s*',line.strip())
        if match:
            values[match[1]]=ast.literal_eval(match[2])
    if any(values.get(k)!=v for k,v in {'result':'values','unit':'metric','datatype':'depth','ser':'ams','type':'pf'}.items()):
        raise ValueError('Expected official AMS precipitation depth in millimetres')
    labels=re.findall(r'<th scope="row" class="tblLbls">\s*(\d+)-(min|hr|day)\s*</th>\s*<td class="tblInner" id="(\d+)-0"',html)
    if len(labels)!=19 or [int(x[2]) for x in labels]!=list(range(19)):
        raise ValueError('Unverified duration labels/order')
    durations=[int(n)*{'min':1,'hr':60,'day':1440}[unit] for n,unit,_ in labels]
    freq_match=re.search(r"hdrArr = (\['1/2'.*?\]);",javascript)
    if not freq_match: raise ValueError('Missing official AMS frequency labels')
    years=[int(v.split('/')[1]) for v in ast.literal_eval(freq_match[1])]
    arrays={k:np.asarray(values[k],dtype=float) for k in ('quantiles','lower','upper')}
    for data in arrays.values():
        if data.shape!=(19,len(years)) or not np.isfinite(data).all() or (data<=0).any():
            raise ValueError('Invalid NOAA values')
        if (np.diff(data,axis=0)<0).any() or (np.diff(data,axis=1)<0).any():
            raise ValueError('Nonmonotonic NOAA depths')
    if not ((arrays['lower']<=arrays['quantiles']).all() and (arrays['quantiles']<=arrays['upper']).all()):
        raise ValueError('Confidence bounds do not enclose estimates')
    return values,durations,years,arrays


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);a=p.parse_args()
    root=a.directory
    values,durations,years,arrays=parse_response((root/'official_response.txt').read_text(),
        (root/'official_page.html').read_text(),(root/'code_gen_16.js').read_text())
    for name,data in arrays.items():
        frame=pd.DataFrame(data,columns=years);frame.insert(0,'duration_min',durations)
        frame.to_csv(root/f'atlas14_ams_{name}_mm.csv',index=False)
    result=dict(status='official data retrieved; site adoption pending',latitude=values['lat'],longitude=values['lon'],
        volume=values['volume'],version=values['version'],series='AMS',units='mm',confidence_percent=90,
        durations_min=durations,return_periods_years=years,production_adoption=False,
        source_url=json.loads((root/'retrieval.json').read_text())['url'],
        source_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in
            [root/'official_response.txt',root/'official_page.html',root/'code_gen_16.js']})
    (root/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
