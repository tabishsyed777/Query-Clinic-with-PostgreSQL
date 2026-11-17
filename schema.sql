CREATE SCHEMA IF NOT EXISTS clinic;
CREATE TABLE IF NOT EXISTS clinic.customers (
 id integer PRIMARY KEY,
 email text NOT NULL UNIQUE,
 name text NOT NULL
);
CREATE TABLE IF NOT EXISTS clinic.products (
 id integer PRIMARY KEY,
 name text NOT NULL,
 price numeric(12,2) NOT NULL CHECK (price > 0)
);
CREATE TABLE IF NOT EXISTS clinic.orders (
 id integer PRIMARY KEY,
 customer_id integer NOT NULL REFERENCES clinic.customers(id),
 product_id integer NOT NULL REFERENCES clinic.products(id),
 ordered_at timestamp NOT NULL,
 quantity integer NOT NULL CHECK (quantity > 0),
 status text NOT NULL CHECK (status IN ('paid','pending','cancelled'))
);
CREATE TABLE IF NOT EXISTS clinic.runs (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 created_at timestamptz NOT NULL DEFAULT now(),
 report jsonb NOT NULL
);
INSERT INTO clinic.customers
SELECT i, 'customer' || i || '@example.test', 'Customer ' || i
FROM generate_series(1,5000) i ON CONFLICT DO NOTHING;
INSERT INTO clinic.products
SELECT i, 'Product ' || i, (100 + i * 37)::numeric / 100
FROM generate_series(1,200) i ON CONFLICT DO NOTHING;
INSERT INTO clinic.orders
SELECT i, 1 + (i * 31 % 5000), 1 + (i * 17 % 200),
 TIMESTAMP '2025-01-01' + (i % 365) * INTERVAL '1 day' + (i % 86400) * INTERVAL '1 second',
 1 + (i % 5), CASE WHEN i % 10 = 0 THEN 'pending' WHEN i % 17 = 0 THEN 'cancelled' ELSE 'paid' END
FROM generate_series(1,100000) i ON CONFLICT DO NOTHING;
ANALYZE clinic.orders;
