from pathlib import Path
import sqlite3
import zipfile
import xml.etree.ElementTree as E
import pytest

ROOT=Path(__file__).resolve().parents[1]
DAY=86_400_000

@pytest.fixture
def db():
    conn=sqlite3.connect(':memory:')
    conn.executescript((ROOT/'sql/01_schema.sql').read_text())
    # User 1 completes; 2 buys before cart; 3 carts a different item; 4 buys late.
    rows=[(0,1,'view',10,None),(DAY,1,'addtocart',10,None),(2*DAY,1,'transaction',10,100),
          (0,1,'view',10,None),(8*DAY,1,'view',10,None),
          (0,2,'view',20,None),(DAY,2,'transaction',20,200),(2*DAY,2,'addtocart',20,None),
          (0,3,'view',30,None),(DAY,3,'addtocart',31,None),
          (0,4,'view',40,None),(DAY,4,'addtocart',40,None),(8*DAY,4,'transaction',40,400),
          (30*DAY,5,'view',50,None)]
    conn.executemany('INSERT INTO raw_events VALUES(?,?,?,?,?)',rows)
    conn.executescript((ROOT/'sql/02_transform.sql').read_text())
    yield conn
    conn.close()

def test_ordered_item_funnel_and_censoring(db):
    assert db.execute('SELECT users FROM funnel ORDER BY stage_order').fetchall()==[(4,),(3,),(1,)]
    assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==13
    assert db.execute('SELECT fully_observed FROM journeys WHERE visitorid=5').fetchone()[0]==0

def test_retention_denominators_and_unknown_future(db):
    assert db.execute('SELECT COUNT(*) FROM retention WHERE fully_observed=0 AND retention_rate IS NOT NULL').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM retention WHERE retention_rate<0 OR retention_rate>1').fetchone()[0]==0
    row=db.execute('SELECT active_users,cohort_size FROM retention WHERE week_number=1 ORDER BY cohort_week LIMIT 1').fetchone()
    assert row==(2,4)  # Users 1 and 4 both return on day 8.

def test_segment_outcome_excludes_early_buyers(db):
    # User 2 bought at exactly 24 h: correctly included as an outcome.
    row=db.execute('SELECT later_purchase FROM early_behavior WHERE visitorid=2').fetchone()
    assert row==(1,)

def test_packaged_tableau_references():
    from src.build_tableau import validate
    validate(ROOT/'tableau/product_funnel.twbx')
