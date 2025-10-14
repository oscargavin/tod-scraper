# LLM Query Translation Architecture
## Natural Language to Precise Database Queries for 100% Product Search

**Status**: Implementation in Progress  
**Last Updated**: 2025-09-01

---

## Implementation Progress

### ✅ Completed
- **Query Translation Module** (`/lib/ai/query-translator.ts`)
  - Dynamic prompt generation using actual product samples
  - Structured output with specs/features separation
  - Conflict resolution and confidence scoring
  
- **Query Builder** (`/lib/db/query-builder.ts`)
  - JSONB query construction for specs and features
  - Full-text search with multi-word support (fixed tsquery syntax error)
  - Price, brand, and quality filters
  - Coverage calculation showing % of products searched

- **Test Infrastructure** (`/app/test-translation/page.tsx` & `/api/test-translation/route.ts`)
  - Test page with example queries
  - API endpoint for translation testing
  - Performance metrics comparison (old vs new)
  - Transparent filter application display

- **Smart Ranking System**
  - Multi-factor scoring (TOD score, features, price)
  - Match reason explanations
  - Preferred feature tracking

### 🚧 Current Issue: JSONB Filtering

**Problem**: JSONB queries returning 0 results despite correct translation

**Root Cause**: Mismatch between expected data format and actual database structure
- Translation expects fields like `capacity` but database has `cotton_capacity_kg`
- String values with units ("8kg") vs numeric values (8)
- Features stored as "Yes"/"No" strings, not booleans
- Using wrong Supabase operators for JSONB queries

**Example**:
```javascript
// What translation generates:
specs_filters: {
  capacity: { in: ["8kg"] }  // Wrong field name
}

// What database has:
specs: {
  cotton_capacity_kg: "8kg"  // Correct field name with unit
}
```

**Research Findings** (via Context7 MCP):
- Supabase uses `contains` operator for JSONB object/array matching
- Need arrow operators (`->` for JSON, `->>` for text) with proper casting
- The `in` operator works differently than expected for JSONB fields

### 🔄 Next Steps
1. Fix JSONB field mapping in query translator
2. Update query builder to use correct Supabase operators
3. Add sample product inspection to understand exact data format
4. Test with all product categories

---

## How It Works (Plain English)

Imagine you're a personal shopping assistant who speaks both human and database. When someone says "I need a quiet washing machine for my small apartment that won't break the bank," you don't run around checking every single washing machine in the store. Instead, you:

1. **Understand** what they really mean:
   - "Quiet" → Look for low noise levels or quiet mark certification
   - "Small apartment" → Compact size, maybe 7kg capacity or less
   - "Won't break the bank" → Budget-friendly, probably under £400

2. **Resolve conflicts** intelligently:
   - If they say "small but for a family of 5" - you know the family size need overrides the "small" preference

3. **Go directly** to the exact products that match:
   - You know where to look and what to look for
   - You don't waste time examining products that don't fit

This is exactly what our LLM Query Translation does - it converts messy human language into precise database filters that find exactly the right products on the first try.

### The Journey of a Query

```
"I want a quiet, energy-efficient washing machine for my family" 
                          ↓
         🧠 LLM understands the intent
                          ↓
    {capacity: 8kg+, noise: <50db, energy: A+++}
                          ↓
         📊 Database finds ALL matching products
                          ↓
    ✨ Results ranked by relevance and quality
                          ↓
         "Here are 23 perfect matches!"
```

---

## The Problem We're Solving

Currently, we:
1. Fetch 200 random products (out of 470+)
2. Send them to an LLM to analyze
3. Hope the right products were in that sample
4. Miss 57% of potentially perfect matches

This is like asking someone to find you a book by only checking 43% of the library shelves!

---

## The Solution: LLM-First Translation

### Core Concept

Instead of using the LLM to analyze products AFTER fetching them, we use it BEFORE to understand exactly what to fetch. The LLM becomes our translator, not our analyzer.

### What Gets Translated

The LLM translates natural language into database-friendly filters across two main data types:

#### 1. **Specs** (Technical Specifications)
These are measurable, objective characteristics:
- `cotton_capacity_kg`: "6kg", "7kg", "8kg", etc.
- `width`, `depth`, `height`: Physical dimensions
- `old_energy_rating`: "A+++", "A++", "A", "B", etc.
- `max_spin_speed_rpm`: "1200", "1400", "1600"
- `annual_energy_cost`: "£45.20", "£62.00"
- `noise_level_db`: Actual noise measurements

#### 2. **Features** (Yes/No Capabilities)
These are binary features a product either has or doesn't:
- `smart`: Smart/WiFi connectivity
- `steam_wash`: Steam cleaning function
- `quiet_mark`: Quiet Mark certification
- `quick_wash`: Quick wash program
- `delicates_or_handwash`: Gentle cycle
- `panel_safety_lock`: Child lock
- `start_end_delay`: Delay timer
- `time_remaining_display`: Shows time left

### Translation Examples

#### Example 1: Complex Family Needs
**Human**: "I need a washing machine that's quiet enough not to wake the baby, can handle loads for a family of 4, has good energy efficiency, and fits in my 60cm wide space"

**LLM Translation**:
```javascript
{
  // Specs filters
  specs_filters: {
    cotton_capacity_kg: { min: 8, max: 10 },  // Family of 4 = 8-10kg
    width: { max: 60 },                       // Must fit in 60cm
    old_energy_rating: ['A+++', 'A++', 'A'],  // Good efficiency
    noise_level_db: { max: 52 }               // Quiet for baby
  },
  
  // Features filters
  features_required: [
    'quiet_mark'  // Additional quiet certification
  ],
  features_preferred: [
    'panel_safety_lock',  // Good with kids
    'start_end_delay'     // Flexibility for family schedule
  ],
  
  // Search strategy
  search_text: 'quiet silent',
  sort_priority: 'noise_then_capacity',
  
  // Conflict resolution
  notes: [
    "Prioritized capacity for family over absolute minimum noise",
    "60cm width is hard constraint, may limit options"
  ]
}
```

#### Example 2: Tech-Savvy User
**Human**: "Latest smart washing machine with all the bells and whistles, I want to control it from my phone"

**LLM Translation**:
```javascript
{
  // Features are primary here
  features_required: [
    'smart',           // Must have app control
    'steam_wash',      // Premium feature
    'steam_refresh',   // Premium feature
    'time_remaining_display'
  ],
  
  // Specs for premium tier
  specs_filters: {
    price: { min: 700 },  // Premium products
    cotton_capacity_kg: { min: 9 }  // Larger premium models
  },
  
  // Ranking
  sort_priority: 'features_count_then_tod_score',
  
  notes: ["User wants maximum features, price not a concern"]
}
```

#### Example 3: Budget Studio Apartment
**Human**: "Cheapest small washer for my studio, just need it to work"

**LLM Translation**:
```javascript
{
  specs_filters: {
    price: { max: 350 },           // Budget constraint
    cotton_capacity_kg: { max: 7 }, // Small for studio
    width: { max: 55 },            // Compact size
    depth: { max: 55 }             // Compact size
  },
  
  features_required: [],  // No specific features needed
  
  // Focus on reliability at low price
  additional_filters: {
    tod_score: { min: 60 }  // "Just need it to work" = reliable
  },
  
  sort_priority: 'price_ascending',
  
  notes: ["Basic functionality prioritized over features"]
}
```

---

## Technical Integration Plan

### Phase 1: Query Translation Module

Create `/lib/ai/query-translator.ts`:

```typescript
interface TranslatedQuery {
  // Specs (JSONB queries on numeric/string values)
  specs_filters: {
    [key: string]: {
      min?: number;
      max?: number;
      exact?: string | number;
      in?: (string | number)[];
    }
  };
  
  // Features (JSONB boolean checks)
  features_required: string[];  // Must have these
  features_preferred: string[]; // Nice to have
  features_excluded: string[];  // Must NOT have
  
  // Additional filters
  price_range?: { min?: number; max?: number };
  brands?: string[];
  tod_score_min?: number;
  
  // Search and sort
  search_text?: string;
  sort_priority: SortStrategy;
  
  // Metadata
  confidence: number;
  notes: string[];
  conflicts_resolved: string[];
}

async function translateQuery(
  userQuery: string,
  categoryId: number,
  conversationContext?: Context
): Promise<TranslatedQuery> {
  
  // Get category-specific context
  const categorySpecs = await getCategorySpecs(categoryId);
  const categoryFeatures = await getCategoryFeatures(categoryId);
  const priceDistribution = await getPriceDistribution(categoryId);
  
  const prompt = `
    You are translating a natural language query into precise database filters.
    
    Category: ${getCategoryName(categoryId)}
    
    Available Specs (with sample values):
    ${JSON.stringify(categorySpecs, null, 2)}
    
    Available Features (Yes/No):
    ${JSON.stringify(categoryFeatures, null, 2)}
    
    Price Distribution:
    - Budget: <£${priceDistribution.q1}
    - Mid-range: £${priceDistribution.q1}-£${priceDistribution.q3}
    - Premium: >£${priceDistribution.q3}
    
    User Query: "${userQuery}"
    ${conversationContext ? `Previous context: ${conversationContext}` : ''}
    
    Translate into filters. Important:
    - Resolve conflicts (e.g., "small but family-sized")
    - Map vague terms to specific values
    - Include both specs AND features
    - Explain your reasoning in notes
  `;
  
  return await generateStructuredOutput<TranslatedQuery>(prompt);
}
```

### Phase 2: Optimized Query Builder

Create `/lib/db/query-builder.ts`:

```typescript
async function buildPreciseQuery(
  translation: TranslatedQuery,
  categoryId: number
): Promise<PostgrestQueryBuilder> {
  
  let query = supabase
    .from('products')
    .select('*')
    .eq('category_id', categoryId);
  
  // Apply specs filters (JSONB queries)
  for (const [spec, filter] of Object.entries(translation.specs_filters)) {
    if (filter.min !== undefined || filter.max !== undefined) {
      // Numeric range query
      const values = await getValuesInRange(spec, filter.min, filter.max);
      query = query.in(`specs->>${spec}`, values);
    } else if (filter.in) {
      // Multiple acceptable values
      query = query.in(`specs->>${spec}`, filter.in);
    } else if (filter.exact !== undefined) {
      // Exact match
      query = query.eq(`specs->>${spec}`, filter.exact);
    }
  }
  
  // Apply required features (must have ALL)
  for (const feature of translation.features_required) {
    query = query.eq(`features->>${feature}`, 'Yes');
  }
  
  // Apply excluded features (must NOT have)
  for (const feature of translation.features_excluded) {
    query = query.or(`features->>${feature}.is.null,features->>${feature}.neq.Yes`);
  }
  
  // Price filter
  if (translation.price_range) {
    if (translation.price_range.min) {
      query = query.gte('price', translation.price_range.min);
    }
    if (translation.price_range.max) {
      query = query.lte('price', translation.price_range.max);
    }
  }
  
  // Brand filter
  if (translation.brands?.length) {
    query = query.in('brand', translation.brands);
  }
  
  // Quality filter
  if (translation.tod_score_min) {
    query = query.gte('tod_score', translation.tod_score_min);
  }
  
  // Full-text search
  if (translation.search_text) {
    query = query.textSearch('search_vector', translation.search_text);
  }
  
  // NO LIMIT - we want ALL matching products
  return query;
}
```

### Phase 3: Smart Ranking System

```typescript
async function rankResults(
  products: Product[],
  translation: TranslatedQuery
): Promise<RankedProduct[]> {
  
  return products.map(product => {
    let score = 0;
    const matchDetails = [];
    
    // Required features (highest weight)
    const requiredMet = translation.features_required.every(
      f => product.features?.[f] === 'Yes'
    );
    if (requiredMet) {
      score += 40;
      matchDetails.push('✓ All required features');
    }
    
    // Preferred features (bonus points)
    const preferredCount = translation.features_preferred.filter(
      f => product.features?.[f] === 'Yes'
    ).length;
    score += (preferredCount / translation.features_preferred.length) * 20;
    
    // TOD Score (quality indicator)
    score += (product.tod_score / 100) * 20;
    
    // Price match (if budget conscious)
    if (translation.sort_priority.includes('price')) {
      const priceScore = calculatePriceScore(product.price, translation.price_range);
      score += priceScore * 20;
    }
    
    return {
      ...product,
      relevance_score: score,
      match_details: matchDetails,
      preferred_features_matched: preferredCount
    };
  })
  .sort((a, b) => b.relevance_score - a.relevance_score);
}
```

### Phase 4: API Integration

Update `/api/chat/route.ts`:

```typescript
// New flow: Translate → Query → Rank → Return
const translatedQuery = await translateQuery(
  userMessage,
  categoryId,
  conversationContext
);

// Build and execute precise query
const query = await buildPreciseQuery(translatedQuery, categoryId);
const { data: allMatchingProducts } = await query;

// Rank all matching products
const rankedProducts = await rankResults(allMatchingProducts, translatedQuery);

// Return with full transparency
return {
  products: rankedProducts.slice(0, 20),
  searchMetadata: {
    totalMatched: allMatchingProducts.length,
    totalInCategory: await getTotalProducts(categoryId),
    searchCoverage: `${(allMatchingProducts.length / totalInCategory * 100).toFixed(1)}%`,
    translation: translatedQuery,
    appliedFilters: {
      specs: Object.keys(translatedQuery.specs_filters),
      requiredFeatures: translatedQuery.features_required,
      preferredFeatures: translatedQuery.features_preferred
    }
  }
};
```

---

## Performance Benefits

### Current System
- Fetches 200 products blindly
- Sends all to LLM for analysis
- ~5000 tokens used
- 2-3 second response time
- Searches 43% of inventory

### New System
- Fetches only matching products
- LLM translates query once
- ~500 tokens used
- <500ms response time
- Searches 100% of inventory

### Token Usage Comparison

**Current**: 
```
40 products × ~125 tokens each = 5000 tokens
```

**New**:
```
1 query translation = 500 tokens
```

**Savings**: 90% reduction in token usage

---

## Implementation Roadmap

### Week 1: Foundation
- [ ] Create query translation schema
- [ ] Build category context system
- [ ] Implement basic translation

### Week 2: Query Building
- [ ] Build JSONB query generator
- [ ] Handle specs vs features
- [ ] Test with all categories

### Week 3: Ranking & Scoring
- [ ] Implement multi-factor ranking
- [ ] Add explanation system
- [ ] Optimize performance

### Week 4: Polish & Deploy
- [ ] Add caching layer
- [ ] Handle edge cases
- [ ] Performance testing
- [ ] Deploy to production

---

## Success Metrics

1. **Coverage**: 100% of relevant products searched (up from 43%)
2. **Speed**: <500ms response time (down from 2-3s)
3. **Accuracy**: 95%+ of results match user intent
4. **Token Usage**: 90% reduction in LLM tokens
5. **User Satisfaction**: Measurable increase in click-through rate

---

## Conclusion

This architecture fundamentally changes how we search products. Instead of hoping the right products are in our sample, we go directly to exactly what the user wants. The LLM becomes our intelligent translator, not our brute-force analyzer.

The result: faster, more accurate, more efficient searches that actually look at 100% of relevant products.

---

*Document Version: 1.0*  
*Created: 2025-08-31*  
*Architecture by: Full-Stack AI Engineering Team*