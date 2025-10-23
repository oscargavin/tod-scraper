#!/usr/bin/env python3
"""
Shared utilities for review enrichment
"""


def calculate_tod_score(rating, count, global_avg=4.0, min_reviews=30):
    """
    Calculate TOD Score: confidence-weighted rating as percentage (0-100)

    Args:
        rating: Product's average rating (e.g., "4.5/5" → 4.5)
        count: Number of reviews
        global_avg: Average rating across all products (default 4.0)
        min_reviews: Minimum reviews for full confidence (default 30)

    Returns:
        tod_score: Weighted rating as percentage (0-100)

    Examples:
        5.0 stars with 2 reviews → ~81 (pulled toward average)
        4.5 stars with 1000 reviews → ~90 (stays near actual rating)
    """
    if not rating or not count:
        return None

    # Convert rating string if needed ("4.5/5" → 4.5)
    if isinstance(rating, str):
        if '/' in rating:
            rating = float(rating.split('/')[0])
        else:
            rating = float(rating)

    # Bayesian average formula
    confidence_score = (count / (count + min_reviews)) * rating + \
                      (min_reviews / (count + min_reviews)) * global_avg

    # Convert to percentage (0-5 scale → 0-100)
    tod_score = (confidence_score / 5.0) * 100

    return round(tod_score, 1)
