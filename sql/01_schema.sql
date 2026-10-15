DROP TABLE IF EXISTS raw_events;
CREATE TABLE raw_events (
    timestamp INTEGER NOT NULL,
    visitorid INTEGER NOT NULL,
    event TEXT NOT NULL CHECK(event IN ('view','addtocart','transaction')),
    itemid INTEGER NOT NULL,
    transactionid INTEGER
);
