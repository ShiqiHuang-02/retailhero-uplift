"""Additive portfolio analysis. Existing models/notebooks/results are read-only.

Run from project root: .venv/bin/python -B scripts/build_portfolio.py
Staging: --source original_project --output staging_project
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os

os.environ.setdefault('MPLCONFIGDIR', '/tmp/retailhero-matplotlib')
os.environ.setdefault('LOKY_MAX_CPU_COUNT', '4')
import duckdb
import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm
from threadpoolctl import threadpool_limits


def estimate(x):
    x = np.asarray(x, dtype=float)
    mean = x.mean() * 1000
    se = x.std(ddof=1) / np.sqrt(len(x)) * 1000
    return mean, mean - 1.96 * se, mean + 1.96 * se


def bootstrap_paired(contributions, reps=3000, seed=20261109):
    """IID customer pairs; fixed models, scores and membership; no re-ranking."""
    x = np.asarray(contributions, dtype=float)
    rng = np.random.default_rng(seed)
    values = np.empty(reps)
    for start in range(0, reps, 40):
        stop = min(start + 40, reps)
        idx = rng.integers(0, len(x), size=(stop-start, len(x)))
        values[start:stop] = x[idx].mean(axis=1) * 1000
    return np.quantile(values, [0.025, 0.975]), values


def dr_score(d, e=0.5):
    return (d.p1-d.p0 + d.treatment_flg/e*(d.target-d.p1)
            - (1-d.treatment_flg)/(1-e)*(d.target-d.p0)).to_numpy(float)


def selection(d, score, share):
    k = round(len(d)*share)
    if score is None:
        return np.full(len(d), k/len(d))
    idx = d.sort_values([score, 'client_id'], ascending=[False, True]).index[:k]
    w = np.zeros(len(d)); w[idx] = 1
    return w


def build(source, output, reps, audit_raw):
    tables = output/'reports/portfolio/tables'
    figures = output/'reports/portfolio/figures'
    data = output/'tableau/data'
    for p in [tables, figures, data]: p.mkdir(parents=True, exist_ok=True)
    checks = {}
    def save(df, name, tableau=True):
        df.to_csv(tables/f'{name}.csv', index=False)
        if tableau: df.to_csv(data/f'{name}.csv', index=False)

    config = json.loads((source/'models/model_config.json').read_text())
    policy = json.loads((source/'models/policy_config.json').read_text())
    frames = {s: duckdb.read_parquet(str(source/f'data/processed/{s}.parquet')).df()
              for s in ['train', 'validation', 'test']}
    checks['split_disjoint'] = all(set(frames[a].client_id).isdisjoint(frames[b].client_id)
        for a,b in [('train','validation'),('train','test'),('validation','test')])
    assert checks['split_disjoint']
    models = {n: joblib.load(source/f'models/{f}.joblib') for n,f in
              [('response_score','response_model'),('p0','tlearner_m0'),('p1','tlearner_m1')]}
    scored = []
    for split in ['validation','test']:
        d = frames[split].copy().reset_index(drop=True)
        for name,model in models.items(): d[name] = model.predict_proba(d[config['feature_columns']])[:,1]
        d['uplift_score'] = d.p1-d.p0
        bins = {c: np.searchsorted(policy['rfm_thresholds'][c], d[c], side='right')
                for c in policy['rfm_thresholds']}
        d['rfm_score'] = 4-bins['recency_days']+bins['txn_count_history']+bins['spend_history']
        d['dr_score'] = dr_score(d)
        d['split'] = split
        scored.append(d)
    combined = pd.concat(scored, ignore_index=True)
    con = duckdb.connect()
    con.execute('SET threads=4')
    con.register('scored_customers', combined)
    con.execute((output/'sql/02_policy_marts.sql').read_text())
    for name in ['policy_summary','selected_profiles','policy_overlap']:
        save(con.table(name).df().sort_values(list(con.table(name).df().columns[:2])), name)
    # Individual-level scores stay local and are excluded from shareable Tableau files.
    customer_path = output/'reports/portfolio/customer_policy_mart.parquet'
    con.sql('SELECT * FROM policy_assignments').write_parquet(str(customer_path))
    summary = con.table('policy_summary').df()
    for split in ['validation','test']:
        old = pd.read_csv(source/f'reports/tables/{split}_policy_results.csv').set_index('strategy').sort_index()
        new = summary.query('split == @split').set_index('strategy').sort_index()
        fields = ['contacts_per_1000','gain_per_1000','ci_low','ci_high']
        err = np.max(np.abs(old[fields].to_numpy()-new[fields].to_numpy()))
        assert err < 1e-8, (split, err)
        checks[f'{split}_original_max_abs_error'] = float(err)
    assignments = con.table('policy_assignments').df()
    assert not assignments.duplicated(['split','client_id','strategy']).any()
    checks['unique_customer_strategy_keys'] = True

    print('SQL marts and original-result reconciliation passed.', flush=True)
    all_customers = pd.concat(frames.values(), ignore_index=True)
    overview = all_customers.groupby('treatment_flg').agg(customers=('target','size'),buyers=('target','sum')).reset_index()
    overview['purchase_rate'] = overview.buyers/overview.customers
    save(overview, 'overall_rates')
    p0,p1 = overview.purchase_rate.to_numpy()
    n0,n1 = overview.customers.to_numpy()
    se = np.sqrt(p0*(1-p0)/n0+p1*(1-p1)/n1)
    save(pd.DataFrame([dict(difference_pp=100*(p1-p0),ci_low_pp=100*(p1-p0-1.96*se),ci_high_pp=100*(p1-p0+1.96*se))]),'overall_difference')

    comparisons=[]; curves=[]; calibration=[]; propensity=[]
    ranks = {'Random':None, **policy['ranking_columns']}
    for d in scored:
        split = d['split'].iloc[0]
        weights = {s:selection(d,c,0.2) for s,c in ranks.items()}
        for baseline in ['Response','Response_p1','Random','RFM']:
            v = (weights['Uplift']-weights[baseline])*d.dr_score.to_numpy()
            mean,low,high = estimate(v)
            row = dict(split=split,comparison=f'Uplift - {baseline}',estimate_per_1000=mean,
                       normal_ci_low=low,normal_ci_high=high,bootstrap_ci_low=np.nan,bootstrap_ci_high=np.nan,
                       bootstrap_reps=0,bootstrap_seed=20261109,
                       analysis_role='primary_existing' if baseline=='Response' else 'exploratory')
            if baseline=='Response':
                bounds, draws = bootstrap_paired(v,reps)
                row.update(bootstrap_ci_low=bounds[0],bootstrap_ci_high=bounds[1],bootstrap_reps=reps)
                if split=='test': np.save(output/'reports/portfolio/bootstrap_primary_draws.npy',draws)
            comparisons.append(row)
        if split=='validation':
            for share in np.linspace(0,1,21):
                for strategy,col in ranks.items():
                    w=selection(d,col,float(share)); mean,low,high=estimate(w*d.dr_score)
                    curves.append(dict(split=split,strategy=strategy,contact_share=float(share),
                        contacts_per_1000=w.mean()*1000,gain_per_1000=mean,ci_low=low,ci_high=high))
            for e in [0.45,0.475,0.5,0.525,0.55]:
                mean,low,high=estimate((weights['Uplift']-weights['Response'])*dr_score(d,e))
                propensity.append(dict(assumed_constant_propensity=e,estimate_per_1000=mean,ci_low=low,ci_high=high))
            ranked=d.sort_values(['uplift_score','client_id']).copy()
            ranked['group']=pd.qcut(np.arange(len(d)),q=5,labels=False)+1
            for g,f in ranked.groupby('group'):
                mean,low,high=estimate(f.dr_score)
                calibration.append(dict(uplift_group=f'Q{g}',customers=len(f),predicted_uplift_pp=f.uplift_score.mean()*100,
                    estimated_uplift_pp=mean/10,ci_low_pp=low/10,ci_high_pp=high/10))
    comparison_df=pd.DataFrame(comparisons)
    save(comparison_df,'paired_comparisons')
    curve=pd.DataFrame(curves);save(curve,'contact_curve')
    save(pd.DataFrame(calibration),'uplift_calibration')
    save(pd.DataFrame(propensity),'propensity_scenarios')
    assert np.allclose(curve.query('contact_share == 0').gain_per_1000,0)
    assert np.ptp(curve.query('contact_share == 1').gain_per_1000)<1e-8
    checks['curve_endpoints'] = True
    overlap=con.table('policy_overlap').df()
    assert np.allclose(overlap.query('strategy_a == strategy_b').jaccard,1)
    checks['overlap_diagonal'] = True
    # Scenario amounts have no observed currency and are explicitly hypothetical.
    scenarios=[]
    for margin in [10.,30.,50.]:
        for cost in [0.1,0.5,1.]:
            z=curve.copy();z['assumed_margin']=margin;z['assumed_contact_cost']=cost
            z['net_value_per_1000']=z.gain_per_1000*margin-z.contacts_per_1000*cost
            z['net_ci_low']=z.ci_low*margin-z.contacts_per_1000*cost
            z['net_ci_high']=z.ci_high*margin-z.contacts_per_1000*cost
            scenarios.append(z)
    scenario=pd.concat(scenarios,ignore_index=True);save(scenario,'cost_scenarios')
    assert np.allclose(scenario.query('contact_share == 0').net_value_per_1000,0)
    checks['zero_contact_zero_cost'] = True

    # Sample-size planning for randomized strategy assignment (not contacted-only).
    sizes=[]
    for baseline in [0.60,0.62,0.65]:
        for delta in [0.003,0.005,0.008]:
            p2=baseline+delta; mid=(baseline+p2)/2
            n=math.ceil(((norm.ppf(.975)*np.sqrt(2*mid*(1-mid))+
                         norm.ppf(.8)*np.sqrt(baseline*(1-baseline)+p2*(1-p2))) / delta)**2)
            sizes.append(dict(assumed_baseline_rate=baseline,mde_pp=delta*100,alpha=.05,power=.8,
                              customers_per_arm=n,total_customers=2*n))
    save(pd.DataFrame(sizes),'experiment_sample_sizes')

    if audit_raw:
        print('Rebuilding transaction features from raw data...',flush=True)
        con.read_csv(str(source/'data/raw/purchases.csv.gz')).create_view('purchases_raw')
        sql=(output/'sql/01_transaction_features.sql').read_text().split(';')
        con.execute(sql[0])
        conflict=con.sql('SELECT COUNT(*) FROM transaction_audit WHERE time_versions != 1 OR store_versions != 1 OR amount_versions != 1 OR missing_amount_rows > 0 OR client_id IS NULL OR transaction_id IS NULL').fetchone()[0]
        assert conflict==0, f'{conflict} conflicting transactions: review before aggregation'
        for statement in sql[1:]:
            if statement.strip(): con.execute(statement)
        rebuilt=con.table('customer_rfm').df().set_index('client_id')
        existing=all_customers.set_index('client_id')
        cols=['recency_days','txn_count_history','spend_history','avg_transaction_amount','txn_count_30d','spend_30d','zero_amount_txn_count']
        a=rebuilt.loc[existing.index,cols].to_numpy(float);b=existing[cols].to_numpy(float)
        assert np.allclose(a,b,rtol=1e-12,atol=1e-8)
        checks['raw_feature_max_abs_error']=float(np.max(np.abs(a-b)))
        checks['transaction_conflicts']=int(conflict)
        checks['raw_transaction_count']=con.sql('SELECT COUNT(*) FROM transactions').fetchone()[0]
        checks['raw_detail_count']=con.sql('SELECT COUNT(*) FROM purchases_raw').fetchone()[0]
    else: checks['raw_features']='not run; use --audit-raw'

    checks['bootstrap_reps']=reps
    checks['bootstrap_scope']='fixed model, fixed scores, fixed selection; IID paired customer resampling'
    checks['tableau_native_validation']='not performed; Tableau unavailable'
    checks['existing_model_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source/'models').glob('*.joblib')}
    (output/'reports/portfolio/validation.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    from portfolio_present import present
    present(output)
    print(json.dumps(checks,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--bootstrap-reps',type=int,default=3000)
    parser.add_argument('--audit-raw',action='store_true')
    args=parser.parse_args()
    if args.bootstrap_reps<100: parser.error('Use at least 100 bootstrap draws; final default is 3000.')
    with threadpool_limits(limits=4):
        build(args.source.resolve(),args.output.resolve(),args.bootstrap_reps,args.audit_raw)
