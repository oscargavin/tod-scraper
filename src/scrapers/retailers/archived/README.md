# Archived Retailer Scrapers

This directory contains retailer scrapers that have been disabled/archived.

## Very Scraper

**Status:** Archived (2025-01-15)

**Reason:** Aggressive anti-bot protection causing consistent `ERR_HTTP2_PROTOCOL_ERROR`

**Coverage:** 661 products (6.9% of catalog)

**Technical Details:**
- Very.co.uk implements aggressive anti-bot measures that trigger HTTP/2 protocol errors in Playwright
- The scraper logic is fully functional (successfully extracted 34 specs in initial tests)
- The URL resolver successfully handles tracking redirects (clicks.trx-hub.com → awin1.com → very.co.uk)
- HTTP2 errors are triggered by:
  - Multiple requests in short timespan
  - Automated browser detection
  - IP-based rate limiting

**Implementation:**
- ✅ Accordion expansion for hidden content
- ✅ Technical specs table extraction
- ✅ Features and description parsing
- ✅ Gemini 2.5 Flash integration for structured data extraction
- ✅ Clean URL handling (strips affiliate parameters)

**Potential Solutions (if re-enabling):**
1. Rate limiting (5-10 seconds between requests)
2. Proxy rotation for IP diversity
3. Residential proxy services
4. Session management and cookie persistence
5. Exponential backoff retry logic
6. Real browser automation (vs headless)

**Test Results:**
- First test: ✅ 34 specs extracted successfully
- Subsequent tests: ❌ HTTP2 protocol errors
- URL resolver: ✅ Always works correctly

The scraper is production-ready but requires infrastructure changes (proxies, rate limiting) to work reliably at scale.
