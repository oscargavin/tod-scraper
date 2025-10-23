"""
URL Resolver Utility
Resolves tracking redirect chains to final destination URLs
"""

import requests
from typing import Optional


def resolve_tracking_url(tracking_url: str, timeout: int = 10, max_redirects: int = 10) -> Optional[str]:
    """
    Follow redirect chain to resolve tracking URL to final destination.

    Handles multi-hop redirects like:
    1. clicks.trx-hub.com (Which.com tracker)
    2. awin1.com (Affiliate network)
    3. very.co.uk (Final destination)

    Args:
        tracking_url: The tracking/affiliate URL to resolve
        timeout: Request timeout in seconds per redirect
        max_redirects: Maximum number of redirects to follow

    Returns:
        Final resolved URL after following all redirects, or None if failed

    Example:
        >>> url = "https://clicks.trx-hub.com/xid/which_c9990_which?q=..."
        >>> resolve_tracking_url(url)
        'https://www.very.co.uk/product/123.prd?utm_campaign=...'
    """
    current_url = tracking_url
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        # Manually follow redirects so we can stop once we reach the final destination
        # without waiting for the full response body
        for i in range(max_redirects):
            try:
                # Use GET with stream=True and manual redirect following
                # stream=True means we don't download the body, just get headers
                response = requests.get(
                    current_url,
                    allow_redirects=False,  # We'll follow manually
                    timeout=timeout,
                    stream=True,
                    headers=headers
                )

                # Check if this is a redirect (3xx status code)
                if 300 <= response.status_code < 400:
                    # Get the Location header
                    next_url = response.headers.get('Location')

                    # Close this response before following redirect
                    response.close()

                    if not next_url:
                        # No Location header, we're done
                        return current_url

                    # Handle relative redirects
                    if next_url.startswith('/'):
                        from urllib.parse import urljoin
                        next_url = urljoin(current_url, next_url)

                    current_url = next_url
                else:
                    # Not a redirect, we've reached the final destination
                    response.close()
                    return current_url

            except requests.exceptions.Timeout:
                # Timeout on this URL - likely the final destination is slow to respond
                # This is common with retail sites that have heavy pages
                # Since we successfully connected (timeout was on reading, not connecting),
                # return this URL as the final destination
                if current_url != tracking_url:
                    # We've made progress through redirects, return current URL
                    return current_url
                else:
                    # Timeout on first request, genuine failure
                    raise

        # Hit max redirects, return what we have
        print(f"Warning: Hit max redirects ({max_redirects}), returning last URL")
        return current_url

    except requests.exceptions.RequestException as e:
        print(f"Failed to resolve tracking URL: {str(e)[:100]}")
        return None
