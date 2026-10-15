-- SQLite 3; timestamps are original Unix milliseconds. Never sample event rows:
-- sampling breaks journeys and understates conversion and retention.
DROP TABLE IF EXISTS events;
CREATE TABLE events AS SELECT DISTINCT * FROM raw_events;
CREATE INDEX idx_journey ON events(visitorid,itemid,event,timestamp);
CREATE INDEX idx_visitor_time ON events(visitorid,timestamp);

DROP TABLE IF EXISTS journeys;
-- Ordered funnel, same visitor AND item, bounded to seven days after first view.
-- Events sharing a timestamp qualify; timestamp granularity cannot order ties.
CREATE TABLE journeys AS
WITH views AS (
  SELECT visitorid,itemid,MIN(timestamp) AS view_ts
  FROM events WHERE event='view' GROUP BY visitorid,itemid
), carts AS (
  SELECT v.*,MIN(e.timestamp) AS cart_ts
  FROM views v LEFT JOIN events e ON e.visitorid=v.visitorid AND e.itemid=v.itemid
    AND e.event='addtocart' AND e.timestamp>=v.view_ts
    AND e.timestamp<=v.view_ts+604800000
  GROUP BY v.visitorid,v.itemid,v.view_ts
)
SELECT c.*,MIN(e.timestamp) AS purchase_ts,
       c.view_ts<=(SELECT MAX(timestamp)-604800000 FROM events) AS fully_observed
FROM carts c LEFT JOIN events e ON e.visitorid=c.visitorid AND e.itemid=c.itemid
  AND e.event='transaction' AND e.timestamp>=c.cart_ts
  AND e.timestamp<=c.view_ts+604800000
GROUP BY c.visitorid,c.itemid,c.view_ts,c.cart_ts;

DROP VIEW IF EXISTS funnel;
CREATE VIEW funnel AS
WITH counts AS (
 SELECT 1 AS stage_order,'Product view' AS stage,COUNT(DISTINCT visitorid) AS users
 FROM journeys WHERE fully_observed=1
 UNION ALL
 SELECT 2,'Add to cart',COUNT(DISTINCT visitorid)
 FROM journeys WHERE fully_observed=1 AND cart_ts IS NOT NULL
 UNION ALL
 SELECT 3,'Purchase',COUNT(DISTINCT visitorid)
 FROM journeys WHERE fully_observed=1 AND purchase_ts IS NOT NULL
), previous AS (
 SELECT *,LAG(users) OVER(ORDER BY stage_order) AS previous_users,
 FIRST_VALUE(users) OVER(ORDER BY stage_order) AS first_users FROM counts
)
SELECT stage_order,stage,users,1.0*users/NULLIF(first_users,0) AS overall_rate,
 1.0*users/NULLIF(previous_users,0) AS step_rate,
 previous_users-users AS dropped_users FROM previous;

DROP VIEW IF EXISTS product_funnel;
CREATE VIEW product_funnel AS
SELECT itemid,COUNT(*) AS viewers,SUM(cart_ts IS NOT NULL) AS cart_users,
 SUM(purchase_ts IS NOT NULL) AS buyers,
 1.0*SUM(purchase_ts IS NOT NULL)/COUNT(*) AS conversion_rate
FROM journeys WHERE fully_observed=1 GROUP BY itemid HAVING COUNT(*)>=50;

DROP TABLE IF EXISTS user_weeks;
-- Monday-aligned UTC week index; Unix day zero was Thursday.
CREATE TABLE user_weeks AS
SELECT DISTINCT visitorid,CAST((timestamp/86400000+3)/7 AS INTEGER) AS week_idx
FROM events;
CREATE INDEX idx_week_user ON user_weeks(visitorid,week_idx);
DROP VIEW IF EXISTS retention;
CREATE VIEW retention AS
WITH cohorts AS (
 SELECT visitorid,MIN(week_idx) AS cohort FROM user_weeks GROUP BY visitorid
), sizes AS (
 SELECT cohort,COUNT(*) AS cohort_size FROM cohorts GROUP BY cohort
), offsets AS (
 SELECT DISTINCT week_idx-(SELECT MIN(week_idx) FROM user_weeks) AS week_number
 FROM user_weeks
), active AS (
 SELECT c.cohort,w.week_idx-c.cohort AS week_number,COUNT(*) AS active_users
 FROM cohorts c JOIN user_weeks w USING(visitorid) GROUP BY c.cohort,week_number
), bounds AS (
 SELECT MIN(week_idx) AS min_week,MAX(week_idx) AS max_week FROM user_weeks
)
SELECT date((s.cohort*7-3)*86400,'unixepoch') AS cohort_week,
 o.week_number,s.cohort_size,
 CASE WHEN s.cohort+o.week_number<b.max_week THEN COALESCE(a.active_users,0) END AS active_users,
 CASE WHEN s.cohort+o.week_number<b.max_week
 THEN 1.0*COALESCE(a.active_users,0)/s.cohort_size END AS retention_rate,
 s.cohort+o.week_number<b.max_week AS fully_observed,
 s.cohort>b.min_week AS complete_acquisition_week
FROM sizes s CROSS JOIN offsets o CROSS JOIN bounds b
LEFT JOIN active a ON a.cohort=s.cohort AND a.week_number=o.week_number
WHERE o.week_number<=12;

DROP TABLE IF EXISTS early_behavior;
-- Feature window is first 24 h; outcome window is subsequent 6 days.
-- Exclude early purchasers to avoid using post-conversion features.
CREATE TABLE early_behavior AS
WITH first_seen AS (
 SELECT visitorid,MIN(timestamp) AS first_ts FROM events GROUP BY visitorid
)
SELECT f.visitorid,
 SUM(e.event='view' AND e.timestamp<f.first_ts+86400000) AS early_views,
 COUNT(DISTINCT CASE WHEN e.event='view' AND e.timestamp<f.first_ts+86400000 THEN e.itemid END) AS early_items,
 MAX(e.event='addtocart' AND e.timestamp<f.first_ts+86400000) AS early_cart,
 MAX(e.event='transaction' AND e.timestamp>=f.first_ts+86400000) AS later_purchase
FROM first_seen f JOIN events e ON e.visitorid=f.visitorid
 AND e.timestamp<=f.first_ts+604800000
WHERE f.first_ts<=(SELECT MAX(timestamp)-604800000 FROM events)
GROUP BY f.visitorid
HAVING MAX(e.event='transaction' AND e.timestamp<f.first_ts+86400000)=0;

DROP VIEW IF EXISTS segments;
CREATE VIEW segments AS
WITH groups AS (
 SELECT 'First-day product views' AS feature,CASE WHEN early_views>=2 THEN '2+ views' ELSE '0-1 views' END AS segment,later_purchase FROM early_behavior
 UNION ALL
 SELECT 'First-day product breadth',CASE WHEN early_items>=2 THEN '2+ products' ELSE '0-1 products' END,later_purchase FROM early_behavior
 UNION ALL
 SELECT 'First-day cart activity',CASE WHEN early_cart=1 THEN 'Cart added' ELSE 'No cart' END,later_purchase FROM early_behavior
)
SELECT feature,segment,COUNT(*) AS users,SUM(later_purchase) AS later_buyers,
 1.0*SUM(later_purchase)/COUNT(*) AS later_purchase_rate
FROM groups GROUP BY feature,segment;
