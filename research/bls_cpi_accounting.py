#!/usr/bin/env python3
"""BLS-CPI calculation research: *accounting* must precede *forecasting*.

Reference:
 https://www.bls.gov/opub/hom/cpi/calculation.htm
 https://www.bls.gov/cpi/factsheets/constructing-special-cpis.htm
 https://www.bls.gov/cpi/factsheets/owners-equivalent-rent-and-rent.htm
 https://www.bls.gov/cpi/seasonal-adjustment/questions-and-answers.htm

This module reproduces the PUBLISHED high-level BLS cost-weight arithmetic
and elementary-index algebra from fully supplied inputs. It CANNOT reproduce
the national CPI release without the underlying price quotes, region-item
weights, seasonal factors and microdata. No claim is made that an arithmetic
aggregation of five seasonally adjusted indices equals published CPI.

The model path is:
  observed/forecast price quote -> basic item-area index ->
  cost-weighted aggregate (unadjusted) -> BLS seasonal process ->
  official-like announced CPI change.

Historical weights and features must have been PUBLISHED by forecast cutoff.
"""
from __future__ import annotations

from datetime import date
import math
import statistics

def number(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def positive(x,name):
    if not number(x) or x<=0:
        raise ValueError(f"{name}: finite positive value required")
    return float(x)

def weighted_geometric_relative(prior_prices,new_prices,expenditure_weights):
    """BLS-style geometric elementary index price relative.
    Sample-level expenditure shares are required; no future or ex-post weights.
    """
    if not (len(prior_prices)==len(new_prices)==len(expenditure_weights)) or not prior_prices:
        raise ValueError("All three price and sample-weight arrays must align")
    p=[positive(x,"prior quote") for x in prior_prices]
    q=[positive(x,"new quote") for x in new_prices]
    w=[positive(x,"sample expenditure weight") for x in expenditure_weights]
    return math.exp(sum(v*math.log(b/a) for a,b,v in zip(p,q,w))/sum(w))

def weighted_laspeyres_relative(prior_prices,new_prices,quantities):
    """Lower-level arithmetic Laspeyres price relative when BLS uses it."""
    if not (len(prior_prices)==len(new_prices)==len(quantities)) or not prior_prices:
        raise ValueError("Array shape mismatch")
    p=[positive(x,"prior quote") for x in prior_prices]
    q=[positive(x,"new quote") for x in new_prices]
    volume=[positive(x,"sample purchase quantity") for x in quantities]
    return sum(b*v for b,v in zip(q,volume))/sum(a*v for a,v in zip(p,volume))

def six_month_housing_index(prev_index,six_month_price_relative):
    """Mechanical BLS 6-panel monthly chaining (does not estimate unknown rent)."""
    return positive(prev_index,"previous index")*positive(
        six_month_price_relative,"6m rent/OER price relative")**(1/6)

def aggregate_cost_weight_change(components,base_month,prior_month,target_month,as_of=None):
    """BLS published cost-weight arithmetic for component aggregation.

    Each component is a DISTINCT mutually exclusive partition of the basket,
    with fields: id, baseCostWeight, baseIndex, priorIndex, targetIndex,
    weightPublishedOn. The original official weights refer to base_month.
    Total cost at t = sum_i CW_{i,b} * I_{i,t} / I_{i,b}; growth = CW_t/CW_t-1-1.
    The 5 top-level CPI families can be used ONLY as APPROXIMATE CPI SA model
    inputs; do not treat them as exact official item-area BLS aggregation.
    """
    if not components:
        raise ValueError("Missing aggregate components")
    if not (base_month<=prior_month<target_month):
        raise ValueError("Invalid base/prior/target chronology")
    if as_of is not None and not (target_month<=as_of):
        raise ValueError("Actual reconstruction cannot claim future index levels")
    ids=set()
    prior_total=target_total=0.0
    details=[]
    for c in components:
        key=c["id"]
        if key in ids:raise ValueError("Double-counted component "+str(key))
        ids.add(key)
        if as_of and c.get("weightPublishedOn","9999-12-31")>as_of:
            raise ValueError("Future dated component cost weight "+str(key))
        if c.get("baseMonth")!=base_month:
            raise ValueError("Mismatched weight reference month "+str(key))
        w=positive(c["baseCostWeight"],"base expenditure weight")
        b=positive(c["baseIndex"],"base index")
        p=positive(c["priorIndex"],"previous index")
        t=positive(c["targetIndex"],"target index")
        cw_prior=w*p/b
        cw_current=w*t/b
        prior_total+=cw_prior
        target_total+=cw_current
        details.append({"id":key,"costWeightBase":w,"costWeightPrior":cw_prior,
                        "costWeightTarget":cw_current,
                        "indexRelative":t/p,"componentGrowthPp":(t/p-1)*100})
    if prior_total<=0:raise ValueError("Zero prior aggregate cost weight")
    contribution=[
        {"id":d["id"],"weightAtPreviousMonth":d["costWeightPrior"]/prior_total,
         "contributionPp":100*(d["costWeightTarget"]-d["costWeightPrior"])/prior_total}
        for d in details]
    change_pct=(target_total/prior_total-1)*100
    check=sum(x["contributionPp"] for x in contribution)
    if abs(check-change_pct)>1e-9:raise AssertionError("Cost-weight reconciliation failed")
    return {"monthlyPercentChange":change_pct,
            "costWeightPrior":prior_total,"costWeightTarget":target_total,
            "contributions":contribution,
            "scope":"supplied components only; nonseasonal basic aggregation",
            "notOfficialSaCpi":True}

def benchmark_bls_beverages():
    """Official BLS published example, December 2022 -> January 2023.

    Beverage materials (coffee + other beverages/tea), nominal December
    expenditure weights and component indexes, to 3 decimal places.
    """
    example=[
        {"id":"coffee","baseMonth":"2022-12","weightPublishedOn":"2023-01-12",
         "baseCostWeight":17367000000,"baseIndex":234.473,
         "priorIndex":234.473,"targetIndex":239.827},
        {"id":"other_beverages","baseMonth":"2022-12","weightPublishedOn":"2023-01-12",
         "baseCostWeight":9638685000,"baseIndex":150.794,
         "priorIndex":150.794,"targetIndex":151.576},
    ]
    result=aggregate_cost_weight_change(example,"2022-12","2022-12","2023-01",
                                        as_of="2023-01-31")
    result["officialBlsPublishedRoundedMonthlyPercentChange"]=1.7
    result["citation"]="https://www.bls.gov/cpi/factsheets/constructing-special-cpis.htm"
    return result

def projection_from_price_relatives(components,base_month,prior_month,target_month,
                                    frozen_at):
    """FORECAST an unadjusted basket from predicted component index RELATIVES.

    Predictions require provenance: model name, source publication cutoff,
    and expected relative. Refuse inputs from after forecast frozen_at.
    This is an accountable aggregation of inputs, NOT a model to forecast
    those inputs or a substitute for missing official seasonal adjustment.
    """
    if target_month<=prior_month:raise ValueError("Target must follow previous period")
    ready=[]
    for c in components:
        if c["inputDataPublishedAt"]>frozen_at:
            raise ValueError("Future source used for CPI category "+str(c["id"]))
        ratio=positive(c["forecastPriceRelative"],"future price relative")
        prior=positive(c["priorIndex"],"previous index")
        ready.append({
            "id":c["id"],"baseMonth":base_month,
            "weightPublishedOn":c["weightPublishedOn"],
            "baseCostWeight":c["baseCostWeight"],
            "baseIndex":c["baseIndex"],"priorIndex":prior,
            "targetIndex":ratio*prior,
        })
    result=aggregate_cost_weight_change(ready,base_month,prior_month,target_month)
    result["forecastFrozenAt"]=frozen_at
    result["status"]="MODEL_COMPONENT_FORECAST_UNVALIDATED"
    return result

if __name__=="__main__":
    import json
    print(json.dumps(benchmark_bls_beverages(),indent=2))
