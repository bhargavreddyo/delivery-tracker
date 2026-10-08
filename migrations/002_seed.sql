-- One order at each stage, so every screen has something on it and the
-- cancellation rule can be tried against a real order both ways: #1 and #2
-- can still be cancelled, #3 onwards cannot.
INSERT INTO orders (id, customer, restaurant, items, total_paise, status, version, placed_at)
SELECT * FROM (VALUES
  (1, 'asha',   'Sagar Tiffin',  '[{"name":"Masala Dosa","paise":12000},{"name":"Filter Coffee","paise":4000}]'::jsonb, 16000, 'placed',           0, now() - INTERVAL '4 minutes'),
  (2, 'vikram', 'Sagar Tiffin',  '[{"name":"Idli Vada","paise":9000}]'::jsonb,                                            9000, 'accepted',         1, now() - INTERVAL '9 minutes'),
  (3, 'priya',  'Biryani House', '[{"name":"Chicken Biryani","paise":28000},{"name":"Raita","paise":5000}]'::jsonb,      33000, 'cooking',          2, now() - INTERVAL '16 minutes'),
  (4, 'rahul',  'Biryani House', '[{"name":"Veg Biryani","paise":22000}]'::jsonb,                                       22000, 'out_for_delivery', 3, now() - INTERVAL '31 minutes'),
  (5, 'fatima', 'Pizza Corner',  '[{"name":"Margherita","paise":31000}]'::jsonb,                                        31000, 'delivered',        4, now() - INTERVAL '70 minutes'),
  (6, 'imran',  'Pizza Corner',  '[{"name":"Garlic Bread","paise":8000}]'::jsonb,                                        8000, 'cancelled',        1, now() - INTERVAL '85 minutes')
) AS v(id, customer, restaurant, items, total_paise, status, version, placed_at)
WHERE NOT EXISTS (SELECT 1 FROM orders);

SELECT setval('orders_id_seq', GREATEST((SELECT MAX(id) FROM orders), 1));

INSERT INTO order_events (order_id, from_status, to_status, actor, at)
SELECT * FROM (VALUES
  (1,'placed','placed','asha',            now() - INTERVAL '4 minutes'),
  (2,'placed','placed','vikram',          now() - INTERVAL '9 minutes'),
  (2,'placed','accepted','kitchen-sagar', now() - INTERVAL '8 minutes'),
  (3,'placed','placed','priya',           now() - INTERVAL '16 minutes'),
  (3,'placed','accepted','kitchen-bh',    now() - INTERVAL '15 minutes'),
  (3,'accepted','cooking','kitchen-bh',   now() - INTERVAL '12 minutes'),
  (4,'placed','placed','rahul',           now() - INTERVAL '31 minutes'),
  (4,'placed','accepted','kitchen-bh',    now() - INTERVAL '30 minutes'),
  (4,'accepted','cooking','kitchen-bh',   now() - INTERVAL '26 minutes'),
  (4,'cooking','out_for_delivery','rider-7', now() - INTERVAL '11 minutes'),
  (5,'placed','placed','fatima',          now() - INTERVAL '70 minutes'),
  (5,'placed','accepted','kitchen-pc',    now() - INTERVAL '69 minutes'),
  (5,'accepted','cooking','kitchen-pc',   now() - INTERVAL '64 minutes'),
  (5,'cooking','out_for_delivery','rider-2', now() - INTERVAL '50 minutes'),
  (5,'out_for_delivery','delivered','rider-2', now() - INTERVAL '38 minutes'),
  (6,'placed','placed','imran',           now() - INTERVAL '85 minutes'),
  (6,'placed','cancelled','imran',        now() - INTERVAL '84 minutes')
) AS v(order_id, from_status, to_status, actor, at)
WHERE NOT EXISTS (SELECT 1 FROM order_events);
