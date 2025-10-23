#!/usr/bin/env python3
"""
Base utilities for sentiment scraping
Common functions used by retailer-specific sentiment scrapers
"""
from typing import Dict, List, Optional


def format_reviews_for_analysis(review_texts: List[str]) -> List[Dict]:
    """
    Convert list of review text strings to format expected by SentimentAnalyzer

    Args:
        review_texts: List of review text strings

    Returns:
        List of review dicts with required fields
    """
    return [
        {
            'text': review_text,
            'title': '',
            'rating': 0,
            'helpful': 0,
            'date': '',
            'reviewer': '',
            'verified': False
        }
        for review_text in review_texts
    ]


def create_sentiment_result(
    sentiment: Dict,
    rating: Optional[float] = None,
    count: Optional[int] = None
) -> Dict:
    """
    Create standardized sentiment result with optional rating/count data

    Args:
        sentiment: Sentiment analysis result from SentimentAnalyzer
        rating: Optional product rating
        count: Optional review count

    Returns:
        Standardized result dict
    """
    result = {
        "summary": sentiment['summary'],
        "pros": sentiment['pros'],
        "cons": sentiment['cons']
    }

    # Add rating/count if provided
    if rating is not None:
        result['rating'] = rating
    if count is not None:
        result['count'] = count

    return result


def get_empty_result(
    message: str = "No reviews found for analysis",
    rating: Optional[float] = None,
    count: Optional[int] = None
) -> Dict:
    """
    Create standardized empty result for when no reviews are found

    Args:
        message: Message to display in summary
        rating: Optional product rating
        count: Optional review count

    Returns:
        Standardized empty result dict
    """
    result = {
        "summary": message,
        "pros": [],
        "cons": []
    }

    if rating is not None:
        result['rating'] = rating
    if count is not None:
        result['count'] = count

    return result
