-- 示例：简易电商库（虚构）
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name VARCHAR(50) NOT NULL,
  phone VARCHAR(20),
  city VARCHAR(30),
  created_at DATETIME
);

CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  title VARCHAR(100) NOT NULL,
  price DECIMAL(10, 2) NOT NULL,
  category VARCHAR(30)
);

CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  status VARCHAR(20) NOT NULL DEFAULT 'paid',
  amount DECIMAL(10, 2),
  created_at DATETIME
);

CREATE TABLE order_items (
  order_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1,
  PRIMARY KEY (order_id, product_id),
  FOREIGN KEY (order_id) REFERENCES orders(id),
  FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX idx_orders_customer ON orders(customer_id);

CREATE TABLE operation_log (
  action VARCHAR(50),
  detail TEXT
);
