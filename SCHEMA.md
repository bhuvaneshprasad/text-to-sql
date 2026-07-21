# Schema Reference

This documents the data model the assistant queries. It is a **Sales / e-commerce** schema: customers place orders for products, products belong to categories and come from suppliers, stock is tracked in inventory, and customers leave reviews.

The full seed defines many more objects (edge-case and scale-test tables, materialized views, functions, triggers). The assistant is deliberately restricted to the nine business tables and three views below - the ones a business user would actually ask about. Everything else is invisible to it.

## How the tables relate

- A **customer** has many **addresses**, many **orders**, and many **reviews**.
- An **order** belongs to one customer and has many **order items**; each item refers to one **product**. Orders reference a shipping and a billing address.
- A **product** belongs to one **category** and one **supplier**, has **inventory** rows (per warehouse), and receives **reviews**.
- **Categories** are self-referential - a category can have a parent category.

`orders` is range-partitioned by year under the hood, and its primary key is
`(id, created_at)`; `order_items` links back to it through `(order_id, order_created_at)`.For querying this behaves like a normal table - the partitioning is a performance detail.

## Tables

### customers
Customer accounts and profiles.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| uuid | uuid | Public unique identifier |
| email | varchar | Unique |
| first_name, last_name | varchar | |
| phone | varchar | |
| date_of_birth | date | |
| gender | char(1) | `M` / `F` / `O` |
| is_active, is_verified | boolean | |
| loyalty_points | integer | |
| preferences | jsonb | See [semi-structured fields](#semi-structured-fields) |
| metadata | hstore | See [semi-structured fields](#semi-structured-fields) |
| created_at, updated_at, last_login_at, deleted_at | timestamptz | `deleted_at` is a soft-delete marker |

### addresses
Billing and shipping addresses. FK `customer_id → customers.id`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| customer_id | integer | Owning customer |
| address_type | enum | `billing` / `shipping` / `both` |
| street_line1, street_line2, city, state, postal_code | varchar | |
| country | char(2) | ISO code, defaults `US` |
| is_default | boolean | |

### categories
Product categories, self-referential for hierarchy. FK `parent_id → categories.id`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| parent_id | integer | Parent category, nullable |
| name | varchar | |
| slug | varchar | Unique |
| description | text | |
| is_active | boolean | |
| sort_order | integer | |

### suppliers
Companies that supply products.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| company_name | varchar | |
| contact_name, contact_email, contact_phone | varchar | |
| country | char(2) | |
| is_active | boolean | |
| rating | numeric(3,2) | 0–5 |

### products
Product catalogue. FKs `category_id → categories.id`, `supplier_id → suppliers.id`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| uuid | uuid | |
| sku | varchar | Unique |
| name | varchar | |
| slug | varchar | Unique |
| description, short_description | text / varchar | |
| category_id, supplier_id | integer | |
| price | numeric(12,2) | |
| cost_price, compare_at_price | numeric(12,2) | |
| currency | char(3) | |
| weight_kg | numeric(8,3) | |
| dimensions | jsonb | Physical size - see below |
| is_active, is_featured, is_digital | boolean | |
| tax_rate | numeric(5,2) | |
| rating_avg | numeric(3,2) | Maintained from approved reviews |
| rating_count | integer | |
| tags | text[] | |
| attributes | jsonb | Category-specific specs - see below |
| images | jsonb | Array of `{url, alt}` |

### inventory
Stock levels per product and warehouse. FK `product_id → products.id`. Unique on `(product_id, warehouse_code)`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| product_id | integer | |
| warehouse_code | varchar | Defaults `MAIN` |
| quantity | integer | On-hand |
| reserved_quantity | integer | Reserved; never exceeds `quantity` |
| reorder_level, reorder_quantity | integer | |
| last_restocked_at | timestamptz | |

### orders
Customer orders (partitioned by year). FKs to `customers` and `addresses`.
Primary key `(id, created_at)`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Part of PK |
| uuid | uuid | |
| order_number | varchar | |
| customer_id | integer | |
| status | enum | `pending`, `confirmed`, `processing`, `shipped`, `delivered`, `cancelled`, `refunded` |
| payment_method | enum | `credit_card`, `debit_card`, `paypal`, `bank_transfer`, `cash`, `crypto` |
| payment_status | varchar | |
| shipping_address_id, billing_address_id | integer | |
| subtotal, tax_amount, shipping_amount, discount_amount, total_amount | numeric(12,2) | |
| currency | char(3) | |
| metadata | jsonb | Usually empty - don't assume keys |
| created_at, updated_at, shipped_at, delivered_at | timestamptz | Different events; don't treat as interchangeable |

### order_items
Line items within an order. FK `product_id → products.id`, and `(order_id, order_created_at) → orders(id, created_at)`.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| order_id, order_created_at | integer / timestamptz | Composite FK to orders |
| product_id | integer | |
| product_name, product_sku | varchar | Snapshot at purchase time |
| quantity | integer | > 0 |
| unit_price | numeric(12,2) | |
| discount_percent, tax_rate | numeric(5,2) | |
| total_price | numeric(12,2) | Line total |

### reviews
Product reviews by customers. FKs to `products` and `customers`. Unique on `(product_id, customer_id)` - one review per customer per product.

| Column | Type | Notes |
|---|---|---|
| id | serial | Primary key |
| product_id, customer_id | integer | |
| order_id | integer | |
| rating | smallint | 1–5 |
| title, content | varchar / text | |
| pros, cons | text[] | |
| is_verified_purchase, is_approved | boolean | Only approved reviews feed `products.rating_avg` |
| helpful_count | integer | |

## Views

These pre-join and aggregate common questions, so the assistant can use them when they fit the grain of a request.

- **v_customer_summary** - one row per customer with order count, lifetime value, average order value, and last order date (cancelled/refunded orders excluded).
- **v_product_inventory** - one row per product with its category, total/reserved/available stock, and a stock status (`in_stock` / `low_stock` / `out_of_stock`).
- **v_top_selling_products** - one row per product that has sold, with order count, units sold, revenue, and rating, ordered by revenue.

## Semi-structured fields

A few columns hold JSON or key-value data. The assistant confirms the exact keys and values against the catalogue before filtering these, but for reference:

- **customers.preferences** (jsonb) - keys `theme` (`dark` / `light` / `auto`),
  `newsletter` (`true` / `false`), `language` (e.g. `en`, `es`, `fr`, `de`, `ja`).
- **customers.metadata** (hstore) - keys `tier` (`bronze` / `silver` / `gold` /
  `platinum`) and `source` (`organic` / `referral` / `ads` / `social`).
- **products.dimensions** (jsonb) - `length`, `width`, `height`, `unit` (`cm` in the seeded data).
- **products.attributes** (jsonb) - category-specific specs; keys vary by product type (e.g. `color`, `storage`, `ram`, `screen_size`, `material`, `sizes`, `author`, `pages`).
- **products.images** (jsonb) - array of `{url, alt}` objects.
- **orders.metadata** (jsonb) - mostly empty; no stable keys to rely on.

## The metadata catalogue

Separately from the business data, bootstrap builds a read-only catalogue in the `text_to_sql_catalog` schema that the assistant queries to ground itself before writing SQL:

- **schema_catalog** - the approved tables/views and their columns, types, and descriptions.
- **relationship_catalog** - the foreign-key relationships and their direction.
- **json_path_catalog** - the keys and paths found inside JSONB columns, and whether each holds an array.
- **value_catalog** - distinct stored values for text columns and JSON paths, so a user's wording can be matched to the value actually stored.

This catalogue is used only to validate identifiers and values - it is never presented as the answer to a user's question.
