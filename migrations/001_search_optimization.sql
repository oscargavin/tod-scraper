-- Search Optimization Migration
-- Adds indexes and full-text search capabilities for high-performance product search

-- 1. Core Performance Indexes
-- Index for category + price queries (most common filter combination)
CREATE INDEX IF NOT EXISTS idx_products_category_price 
ON products(category_id, price);

-- Index for TOD score sorting (frequently used for ranking)
CREATE INDEX IF NOT EXISTS idx_products_tod_score 
ON products(tod_score DESC NULLS LAST);

-- Composite index for brand filtering within categories
CREATE INDEX IF NOT EXISTS idx_products_category_brand 
ON products(category_id, brand);

-- 2. Full-Text Search Setup
-- Add generated search vector column combining all searchable text
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS search_vector tsvector 
GENERATED ALWAYS AS (
  to_tsvector('english',
    COALESCE(name, '') || ' ' ||
    COALESCE(brand, '') || ' ' ||
    COALESCE(model, '') || ' ' ||
    COALESCE((specs)::text, '') || ' ' ||
    COALESCE((features)::text, '')
  )
) STORED;

-- Create GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_products_search 
ON products USING GIN(search_vector);

-- 3. JSONB Indexes for specs and features
-- Allows efficient queries on JSONB fields
CREATE INDEX IF NOT EXISTS idx_products_specs 
ON products USING GIN(specs);

CREATE INDEX IF NOT EXISTS idx_products_features 
ON products USING GIN(features);

-- 4. Partial Indexes for Common Queries
-- Budget washing machines (under £500)
CREATE INDEX IF NOT EXISTS idx_washing_machines_budget 
ON products(price, tod_score DESC) 
WHERE category_id = 1 AND price < 500;

-- Premium washing machines (over £700)
CREATE INDEX IF NOT EXISTS idx_washing_machines_premium 
ON products(price, tod_score DESC) 
WHERE category_id = 1 AND price >= 700;

-- Budget fridge freezers (under £600)
CREATE INDEX IF NOT EXISTS idx_fridge_freezers_budget 
ON products(price, tod_score DESC) 
WHERE category_id = 4 AND price < 600;

-- High-rated products (TOD score >= 80)
CREATE INDEX IF NOT EXISTS idx_high_rated_products 
ON products(category_id, tod_score DESC) 
WHERE tod_score >= 80;

-- 5. Analyze tables to update statistics
ANALYZE products;

-- Verify indexes were created
SELECT 
  schemaname,
  tablename,
  indexname,
  indexdef
FROM pg_indexes
WHERE tablename = 'products'
ORDER BY indexname;