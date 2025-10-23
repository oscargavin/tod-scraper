#!/usr/bin/env python3
"""
Amazon Sentiment Scraper
Extracts Amazon's AI-generated review summary and reformats via Gemini
"""
import asyncio
from typing import Dict
from src.reviews.amazon.scraper import extract_review_data
from src.reviews.sentiment import SentimentAnalyzer


async def get_sentiment_analysis(product_url: str) -> Dict:
    """
    Extract Amazon's review summary and reformat via Gemini

    Amazon already provides AI-generated sentiment analysis on product pages.
    We extract it and pass through Gemini to match our format (summary, pros, cons).

    Returns:
        Dict with rating, count, summary, pros, and cons
    """
    print("Extracting Amazon review data...")

    # Get Amazon's existing AI summary and rating/count
    review_data = await extract_review_data(product_url)

    if not review_data or not review_data.get('amazonSummary'):
        return {
            "rating": review_data.get('rating') if review_data else None,
            "count": review_data.get('count') if review_data else 0,
            "summary": "No reviews found for analysis",
            "pros": [],
            "cons": []
        }

    rating = review_data['rating']
    count = review_data['count']
    amazon_summary = review_data['amazonSummary']
    aspects = review_data.get('aspects', [])

    print(f"Found {count:,} ratings ({rating}/5)")
    print("Reformatting Amazon's AI summary via Gemini...")

    # Reformat Amazon's summary through Gemini
    analyzer = SentimentAnalyzer()

    # Create a pseudo-review from Amazon's summary for Gemini to analyze
    pseudo_review = [{
        'text': f"Amazon AI Summary: {amazon_summary}\n\nMentioned aspects: {', '.join(aspects)}",
        'title': '',
        'rating': rating,
        'helpful': count,
        'date': '',
        'reviewer': 'Amazon AI',
        'verified': True
    }]

    sentiment = await analyzer.analyze_reviews(pseudo_review, "Product", "product")

    # Return in standard format with Amazon rating/count
    return {
        "rating": f"{rating}/5",
        "count": count,
        "summary": sentiment['summary'],
        "pros": sentiment['pros'],
        "cons": sentiment['cons']
    }


async def main():
    """Example usage"""
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python sentiment_scraper.py <amazon_product_url>")
        print("Example: python sentiment_scraper.py https://www.amazon.co.uk/dp/B0CM43QN7V")
        sys.exit(1)

    product_url = sys.argv[1]

    result = await get_sentiment_analysis(product_url)

    # Pretty print the result
    print("\n" + "="*60)
    print("AMAZON REVIEW ANALYSIS")
    print("="*60)

    print(f"\nRATING: {result.get('rating', 'N/A')}")
    print(f"REVIEW COUNT: {result.get('count', 0):,}")

    print(f"\nSUMMARY:\n{result['summary']}")

    print("\nPROS:")
    for pro in result['pros']:
        print(f"  ✓ {pro}")

    print("\nCONS:")
    for con in result['cons']:
        print(f"  ✗ {con}")

    # Also output as clean JSON
    print("\n\nJSON OUTPUT:")
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
