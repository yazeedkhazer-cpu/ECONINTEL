#!/usr/bin/env python3
"""Optional BLS CES Table B total-private 1-month employment diffusion.

Source: https://www.bls.gov/web/empsit/ceseesummary.htm
This is a *published official* index, not a proxy derived from NFP.
If the website changes structure, refuse to publish rather than guessing.
"""
from __future__ import annotations
from html.parser import HTMLParser
import re
import urllib.request

URL = 'https://www.bls.gov/web/empsit/ceseesummary.htm'
_MONTHS = {
    'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,
    'aug':8,'sep':9,'oct':10,'nov':11,'dec':12
}

class _TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]; self._table=0; self._row=None; self._cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'table': self._table += 1
        if self._table and tag == 'tr': self._row=[]
        if self._row is not None and tag in ('th','td'): self._cell=[]
        if self._cell is not None and tag in ('br','p'): self._cell.append(' ')
    def handle_data(self, data):
        if self._cell is not None: self._cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self._cell is not None and self._row is not None:
            self._row.append(' '.join(''.join(self._cell).split()));self._cell=None
        if tag == 'tr' and self._row is not None:
            if self._row:self.rows.append(self._row)
            self._row=None;self._cell=None
        if tag == 'table': self._table=max(0,self._table-1)

def _header_month(s):
    text=' '.join(s.replace('\xa0',' ').split())
    match=re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(20\d{2})\b',text,re.I)
    if not match:return None
    return f'{int(match.group(2)):04d}-{_MONTHS[match.group(1)[:3].lower()]:02d}'

def parse_table(html:str, expected_month:str):
    if not isinstance(html,str) or len(html)<30:raise ValueError('BLS summary HTML missing')
    p=_TableRows();p.feed(html)
    headers=None;data=None;in_diffusion=False;in_private=False
    for row in p.rows:
        # Header must explicitly date each value. Do NOT infer from fetch timestamp.
        if row and row[0].strip().lower()=='category':
            maybe=[_header_month(c) for c in row[1:]]
            if len(maybe)>=3 and all(maybe):headers=maybe
        head=row[0].lower().strip() if row else ''
        if 'diffusion indexes' in head:
            in_diffusion=True;in_private=False;continue
        if not in_diffusion:continue
        if head == 'total private':in_private=True;continue
        if head == 'manufacturing':in_private=False
        if in_private and re.match(r'^over\s+1[\s-]*month\s+span',head):
            data=row[1:];break
    if not headers or not data or len(headers)!=len(data):
        raise ValueError('BLS summary diffusion table or column labels were not recognized')
    if headers[-1]!=expected_month:
        raise ValueError(f'BLS diffusion reference {headers[-1]} does not match payroll {expected_month}')
    if len(set(headers))!=len(headers):raise ValueError('Duplicate BLS month labels')
    if headers!=sorted(headers):raise ValueError('Out of order BLS month labels')
    history=[]
    for month,value in zip(headers,data):
        try: val=float(value.replace(',','').replace('(p)','').strip())
        except ValueError as exc:raise ValueError('Non-numeric BLS diffusion value') from exc
        if not (0<=val<=100):raise ValueError('BLS diffusion must be between 0 and 100')
        history.append([month,val])
    return {'value':history[-1][1], 'date':history[-1][0], 'history':history,
            'source':'BLS · CES Table B · total private / 1-month',
            'seriesId':'BLS:CES:SUMMARY_B:DIFFUSION:PRIVATE:1M','status':'api',
            'frequency':'monthly','unit':'index','sourceUrl':URL}

def fetch(expected_month:str):
    req=urllib.request.Request(URL,headers={'User-Agent':'ECONINTEL academic research dashboard (public BLS table)'})
    with urllib.request.urlopen(req,timeout=30) as r:
        html=r.read().decode('utf-8','replace')
    return parse_table(html,expected_month)
