-- 示例：包含常见问题的查询（用于演示 lint）
SELECT * FROM orders WHERE YEAR(created_at) = 2026;
SELECT o.id, c.name FROM orders o, customers c WHERE o.customer_id = c.id;
SELECT id, name FROM customers WHERE phone LIKE '%8888' OR city = '上海';
SELECT id FROM customers WHERE id NOT IN (SELECT customer_id FROM orders);
UPDATE orders SET status = 'closed';
DELETE FROM orders WHERE status = NULL;
INSERT INTO customers VALUES (1, '张三', '13800000000', '上海', '2026-01-01');
SELECT id, title FROM products ORDER BY price DESC LIMIT 20 OFFSET 50000;
SELECT id, title, price FROM products WHERE category = 'book' ORDER BY price LIMIT 10;
