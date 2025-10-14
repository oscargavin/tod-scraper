-- Smart Product Search Function
-- Performs intelligent product search with relevance scoring

CREATE OR REPLACE FUNCTION search_products_smart(
  p_category_id INTEGER,
  p_search_text TEXT DEFAULT NULL,
  p_price_min NUMERIC DEFAULT NULL,
  p_price_max NUMERIC DEFAULT NULL,
  p_brands TEXT[] DEFAULT NULL,
  p_limit INTEGER DEFAULT 200
)
RETURNS TABLE (
  id INTEGER,
  category_id INTEGER,
  name TEXT,
  brand TEXT,
  model TEXT,
  price NUMERIC,
  tod_score INTEGER,
  specs JSONB,
  features JSONB,
  images JSONB,
  source_url TEXT,
  relevance_score NUMERIC,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
) 
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    p.id,
    p.category_id,
    p.name,
    p.brand,
    p.model,
    p.price,
    p.tod_score,
    p.specs,
    p.features,
    p.images,
    p.source_url,
    -- Calculate relevance score combining multiple factors
    (
      -- Full-text search relevance (0-1, scaled to 0-40)
      CASE 
        WHEN p_search_text IS NOT NULL THEN 
          COALESCE(ts_rank(p.search_vector, websearch_to_tsquery('english', p_search_text)), 0) * 40
        ELSE 0
      END +
      
      -- Price match score (0-30)
      CASE 
        WHEN p_price_min IS NOT NULL AND p_price_max IS NOT NULL THEN
          CASE 
            WHEN p.price BETWEEN p_price_min AND p_price_max THEN 30
            WHEN p.price < p_price_min THEN 
              GREATEST(0, 30 - (p_price_min - p.price) / 50)
            ELSE 
              GREATEST(0, 30 - (p.price - p_price_max) / 50)
          END
        WHEN p_price_max IS NOT NULL THEN
          CASE 
            WHEN p.price <= p_price_max THEN 30
            ELSE GREATEST(0, 30 - (p.price - p_price_max) / 50)
          END
        ELSE 0
      END +
      
      -- Brand preference score (0-20)
      CASE 
        WHEN p_brands IS NOT NULL AND p.brand = ANY(p_brands) THEN 20
        ELSE 0
      END +
      
      -- TOD quality score (0-10)
      COALESCE(p.tod_score::NUMERIC / 10, 0)
    )::NUMERIC AS relevance_score,
    p.created_at,
    p.updated_at
  FROM products p
  WHERE 
    -- Category filter (required)
    p.category_id = p_category_id
    
    -- Full-text search filter
    AND (p_search_text IS NULL OR 
         p.search_vector @@ websearch_to_tsquery('english', p_search_text))
    
    -- Price filters
    AND (p_price_min IS NULL OR p.price >= p_price_min)
    AND (p_price_max IS NULL OR p.price <= p_price_max)
    
    -- Brand filter
    AND (p_brands IS NULL OR p.brand = ANY(p_brands))
  
  -- Order by combined relevance score
  ORDER BY relevance_score DESC, p.tod_score DESC NULLS LAST
  
  -- Limit results
  LIMIT p_limit;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION search_products_smart TO anon, authenticated;

-- Example usage:
-- SELECT * FROM search_products_smart(
--   p_category_id := 1,
--   p_search_text := 'quiet large capacity',
--   p_price_max := 600,
--   p_brands := ARRAY['Bosch', 'Samsung'],
--   p_limit := 50
-- );