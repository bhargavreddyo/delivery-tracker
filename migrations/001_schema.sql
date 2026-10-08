CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer TEXT NOT NULL,
    restaurant TEXT NOT NULL,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_paise BIGINT NOT NULL CHECK (total_paise > 0),
    status TEXT NOT NULL DEFAULT 'placed'
        CHECK (status IN ('placed','accepted','cooking','out_for_delivery',
                          'delivered','cancelled')),
    -- bumped by every accepted transition, so a client can tell a stale read
    version INT NOT NULL DEFAULT 0,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS order_events (
    id BIGSERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    at TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE INDEX IF NOT EXISTS orders_open ON orders (restaurant, status, placed_at);
CREATE INDEX IF NOT EXISTS order_events_order ON order_events (order_id, id);
