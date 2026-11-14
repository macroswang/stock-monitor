"""Walk-forward model research for the shared MA250 detector.

Every test year is predicted by a model trained only on earlier signals. Features
are measured at the signal close; labels are the next-open 20-day net return.
This is research-only: no model is deployed, and the hand-built strong rule is
shown for context even though it was designed on the full sample.
"""
import io, json, statistics, sys, contextlib
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from scripts.study_ma250_large import load, build, apply_variant, base
from core.ma250_pullback import rule_spec

DATA = BASE / 'docs' / 'ma250-pullback' / 'data'
OUT = BASE / 'docs' / 'ma250-pullback' / 'fixed-v3'
FEATURES = ['slope60_pct', 'slope120_pct', 'strength_pct', 'pullback_pct', 'depth_pct', 'reclaim_pct',
            'touch_lag', 'vol_touch_ratio', 'vol_signal_ratio', 'vol_pullback_ratio', 'range_pos',
            'atr20_pct', 'index_above_ma250', 'index_above_ma20', 'index_ret20', 'relative20',
            'breadth', 'industry_rel20', 'higher_low', 'engulf']


def strong29(row):
    return row['strong']


def matrix(rows):
    out = []
    for row in rows:
        values = []
        for key in FEATURES:
            value = row.get(key)
            if isinstance(value, bool):
                value = 1.0 if value else 0.0
            values.append(np.nan if value is None else float(value))
        out.append(values)
    return np.array(out, dtype=float)


def impute(train, test):
    # A fully missing research feature has no training median; keep it neutral.
    med = np.array([np.median(col[np.isfinite(col)]) if np.isfinite(col).any() else 0.
                    for col in train.T])
    return np.where(np.isnan(train), med, train), np.where(np.isnan(test), med, test)


def safe_mean(values):
    return float(np.mean(values)) if len(values) else None


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        _, series, index_map, _ = load(DATA / 'tencent')
        table, _ = build(series, index_map)
    rows = [row for row in apply_variant(table, base) if row['forward'].get('20') is not None]
    breadth = json.loads((BASE / 'docs' / 'ma250-pullback' / 'large' / 'breadth.json').read_text(encoding='utf-8'))['days']
    industry = json.loads((BASE / 'docs' / 'ma250-pullback' / 'large' / 'industry.json').read_text(encoding='utf-8'))['industries']
    # Industry median 20-day return by date; at least five names in the group.
    returns = defaultdict(list)
    for code, bars in series.items():
        closes = [bar['close'] for bar in bars]
        group = industry.get(code)
        if not group:
            continue
        for index in range(20, len(bars)):
            returns[(bars[index]['date'], group)].append((closes[index] / closes[index - 20] - 1) * 100)
    median = {key: statistics.median(values) for key, values in returns.items() if len(values) >= 5}
    for row in rows:
        row['breadth'] = breadth.get(row['date'], {}).get('pct')
        group = industry.get(row['code'])
        row['industry_rel20'] = None
        if group:
            # The candidate's stock return is in relative20 only when the index exists;
            # recompute the stock 20-day return from the panel instead.
            bars = series[row['code']]
            index = row['index']
            if index >= 20:
                stock_ret = (bars[index]['close'] / bars[index - 20]['close'] - 1) * 100
                reference = median.get((row['date'], group))
                row['industry_rel20'] = stock_ret - reference if reference is not None else None
    rows.sort(key=lambda row: row['date'])
    X, y, r = matrix(rows), np.array([1.0 if row['forward']['20'] > 0 else 0.0 for row in rows]), \
        np.array([row['forward']['20'] for row in rows])
    report = dict(rule=rule_spec(), signals=len(rows), features=FEATURES, years={}, aggregate={}, threshold_policy='fixed 0.50 / 0.60; no future-year quantiles')
    predictions = {'logistic': np.full(len(rows), np.nan), 'forest': np.full(len(rows), np.nan)}
    for year in range(2022, 2027):
        train = [index for index, row in enumerate(rows) if row['date'] < f'{year}-01-01' and (row.get('label_end') or '9999') < f'{year}-01-01']
        test = [index for index, row in enumerate(rows) if row['date'].startswith(str(year))]
        if len(train) < 150 or len(test) < 40 or len(set(y[train])) < 2:
            continue
        train_X, test_X = impute(X[train], X[test])
        mean, std = train_X.mean(axis=0), train_X.std(axis=0)
        std[std == 0] = 1
        train_X, test_X = (train_X - mean) / std, (test_X - mean) / std
        year_report = dict(train=len(train), test=len(test), base_win=float(y[test].mean()),
                           base_mean=float(r[test].mean()),
                           strong=dict(n=0, win=None, mean=None))
        strong_test = [index for index in test if strong29(rows[index])]
        if strong_test:
            year_report['strong'] = dict(n=len(strong_test), win=float(y[strong_test].mean()),
                                         mean=float(r[strong_test].mean()))
        for name, model in (
                ('logistic', LogisticRegression(C=0.5, max_iter=2000, class_weight='balanced', random_state=7)),
                ('forest', RandomForestClassifier(n_estimators=300, max_depth=3, min_samples_leaf=15,
                                                  random_state=7, n_jobs=-1))):
            model.fit(train_X, y[train])
            probability = model.predict_proba(test_X)[:, 1]
            predictions[name][test] = probability
            threshold = 0.50
            top = [index for index, value in zip(test, probability) if value >= threshold]
            year_report[name] = dict(auc=float(roc_auc_score(y[test], probability)) if len(set(y[test]))>1 else None,
                                     top_n=len(top), top_win=float(y[top].mean()) if top else None,
                                     top_mean=float(r[top].mean()) if top else None)
        report['years'][str(year)] = year_report
    for name in ('logistic', 'forest'):
        mask = np.isfinite(predictions[name])
        if not mask.any():
            continue
        ranked = predictions[name].copy()
        oos = np.where(mask)[0]
        cutoff = 0.50
        top = [index for index in oos if ranked[index] >= cutoff]
        strong = [index for index in oos if strong29(rows[index])]
        report['aggregate'][name] = dict(
            oos=len(oos), auc=float(roc_auc_score(y[oos], ranked[oos])),
            base_win=float(y[oos].mean()), base_mean=float(r[oos].mean()),
            top_n=len(top), top_win=safe_mean(y[top]), top_mean=safe_mean(r[top]),
            threshold60_n=len([index for index in oos if ranked[index] >= 0.60]),
            threshold60_win=safe_mean([y[index] for index in oos if ranked[index] >= 0.60]),
            threshold60_mean=safe_mean([r[index] for index in oos if ranked[index] >= 0.60]),
            strong_n=len(strong), strong_win=float(y[strong].mean()) if strong else None,
            strong_mean=float(r[strong].mean()) if strong else None)
    model = RandomForestClassifier(n_estimators=400, max_depth=3, min_samples_leaf=15, random_state=7, n_jobs=-1)
    model.fit(np.nan_to_num(X, nan=0.0), y)
    report['importance'] = sorted(zip(FEATURES, model.feature_importances_), key=lambda item: -item[1])[:12]
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT / 'ml.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False), encoding='utf-8')
    print('signals',len(rows));print(json.dumps(report['aggregate'],ensure_ascii=False))


if __name__ == '__main__':
    main()
