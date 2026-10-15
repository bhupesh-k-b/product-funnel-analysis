"""Load the complete clickstream, execute SQL, and export dashboard data."""
from pathlib import Path
import json
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]

def run(raw=None):
    raw = Path(raw) if raw else ROOT / 'data/raw/events.csv'
    output = ROOT / 'data/processed'
    reports = ROOT / 'reports'
    output.mkdir(parents=True, exist_ok=True)
    reports.mkdir(exist_ok=True)
    database = output / 'analytics.sqlite'
    with sqlite3.connect(database) as conn:
        conn.executescript((ROOT / 'sql/01_schema.sql').read_text())
        source_rows = 0
        for chunk in pd.read_csv(raw, chunksize=200_000):
            required = {'timestamp','visitorid','event','itemid','transactionid'}
            if set(chunk.columns) != required:
                raise ValueError(f'Expected columns {sorted(required)}')
            if chunk[['timestamp','visitorid','event','itemid']].isna().any().any():
                raise ValueError('Required event fields cannot be missing')
            chunk.to_sql('raw_events', conn, if_exists='append', index=False)
            source_rows += len(chunk)
        conn.executescript((ROOT / 'sql/02_transform.sql').read_text())
        tables = {}
        for view in ['funnel','retention','product_funnel','segments']:
            tables[view] = pd.read_sql_query(f'SELECT * FROM {view}', conn)
            tables[view].to_csv(output / f'{view}.csv', index=False)
        audit = pd.read_sql_query('SELECT COUNT(*) AS events,COUNT(DISTINCT visitorid) AS visitors,MIN(timestamp) AS start_ms,MAX(timestamp) AS end_ms FROM events', conn).iloc[0].to_dict()
        audit = {key: int(value) for key,value in audit.items()}
        audit.update(source_rows=source_rows, duplicate_events_removed=source_rows-audit['events'])
        audit['eligible_journeys'] = conn.execute('SELECT COUNT(*) FROM journeys WHERE fully_observed=1').fetchone()[0]
    (reports / 'metrics.json').write_text(json.dumps(audit, indent=2)+'\n')
    f = tables['funnel']
    assert f.users.is_monotonic_decreasing, 'Funnel stages must be nested'
    r = tables['retention']
    assert r.loc[r.fully_observed.eq(0),'retention_rate'].isna().all()
    assert r.retention_rate.dropna().between(0,1).all()
    plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False})
    fig, axes = plt.subplots(1,2,figsize=(14,5),layout='constrained')
    axes[0].barh(f.stage[::-1],f.users[::-1],color=['#14b8a6','#3b82f6','#1e293b'])
    axes[0].set_title('Ordered 7-day product funnel',loc='left',fontweight='bold')
    axes[0].set_xlabel('Unique visitors; complete 7-day observation')
    for i,row in enumerate(f.iloc[::-1].itertuples()):
        if row.users>f.users.max()*.5:
            axes[0].text(row.users*.98,i,f'{row.users:,}',va='center',ha='right',color='white',fontsize=9)
        else:
            axes[0].text(row.users,i,f'  {row.users:,}',va='center',fontsize=9)
    pivot = r.loc[r.complete_acquisition_week.eq(1)].pivot(index='cohort_week',columns='week_number',values='retention_rate')
    im=axes[1].imshow(pivot.iloc[:,1:9],aspect='auto',cmap='Blues',vmin=0,vmax=.1)
    axes[1].set_yticks(range(len(pivot)),pivot.index,fontsize=7)
    axes[1].set_xticks(range(8),range(1,9))
    axes[1].set_title('Weekly returning visitors',loc='left',fontweight='bold')
    axes[1].set_xlabel('Weeks since first observed activity; white = censored')
    fig.colorbar(im,ax=axes[1],format=matplotlib.ticker.PercentFormatter(1))
    fig.savefig(reports/'overview.png',dpi=160)
    plt.close(fig)
    lines=['# Findings','',f"Analyzed {audit['events']:,} distinct observed events from {audit['visitors']:,} visitors.",'', '## Ordered funnel','']
    lines += [f'- {row.stage}: {row.users:,} visitors ({row.overall_rate:.2%} of eligible viewers).' for row in f.itertuples()]
    lines += ['', '## Three behavioral signals','', 'Features are measured in the first 24 hours, before the purchase outcome in days 2–7. Early purchasers are excluded. These are associations, not causal drivers.','']
    lines += [f'- {row.feature}, {row.segment}: {row.later_purchase_rate:.3%} later purchase rate (n={row.users:,}).' for row in tables['segments'].itertuples()]
    lines += ['', '## Product priorities','', '1. Investigate product-detail clarity and add-to-cart friction at the largest absolute drop-off.', '2. Test cart recovery and onboarding reminders in a randomized experiment; use purchase conversion and opt-out rate as success/guardrail metrics.', '3. Validate the above signals in a time-separated cohort before using them for targeting.','', 'No onboarding intervention or A/B assignment exists in this source. It cannot establish an 18% conversion lift or a 9% retention improvement. Revenue amounts and referral events are unavailable.']
    (reports/'findings.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(audit,indent=2))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path)
    run(parser.parse_args().input)
