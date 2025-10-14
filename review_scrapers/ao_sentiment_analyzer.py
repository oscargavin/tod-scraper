#!/usr/bin/env python3
"""
AO.com Review Sentiment Analyzer using Gemini
Analyzes review content to extract sentiment, pros, cons, and insights
"""
import os
import json
from typing import Dict, List, Optional
import google.generativeai as genai
from dotenv import load_dotenv


class SentimentAnalyzer:
    """Analyzes product reviews using Gemini to extract sentiment and insights"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the sentiment analyzer
        
        Args:
            api_key: Gemini API key (if not provided, uses GEMINI_API_KEY env var)
        """
        load_dotenv()
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    def build_analysis_prompt(self, reviews: List[Dict], product_name: str, category: str = "product") -> str:
        """
        Build the prompt for Gemini to analyze reviews
        
        Args:
            reviews: List of review dicts
            product_name: Name of the product
            category: Product category for context
        
        Returns:
            Formatted prompt string
        """
        # Prepare review text
        review_texts = []
        for i, review in enumerate(reviews[:50], 1):  # Limit to first 50 reviews
            review_text = f"Review {i} ({review['rating']}/5 stars"
            if review['verified']:
                review_text += ", verified purchase"
            review_text += "):\n"
            
            if review['title']:
                review_text += f"Title: {review['title']}\n"
            
            review_text += f"Text: {review['text']}\n"
            
            if review['helpful'] > 0:
                review_text += f"({review['helpful']} people found this helpful)\n"
            
            review_texts.append(review_text)
        
        prompt = f"""You are an expert product analyst analyzing customer reviews for UK consumers.
Analyze these reviews for the {product_name} ({category}) and provide comprehensive sentiment analysis.

REVIEWS TO ANALYZE:
{chr(10).join(review_texts)}

ANALYSIS INSTRUCTIONS:
1. Analyze the overall sentiment across all reviews
2. Identify the most frequently mentioned pros (positive aspects)
3. Identify the most frequently mentioned cons (negative aspects)  
4. Extract key themes and patterns in the reviews
5. Provide category-specific insights for this {category}

Consider:
- Weight reviews with more helpful votes as more important
- Look for patterns across multiple reviews
- Be specific and actionable in your insights
- Focus on aspects that would matter to potential buyers

Return ONLY valid JSON in this exact format:
{{
  "summary": "<2-3 sentence overall sentiment summary>",
  "pros": ["<specific pro 1>", "<specific pro 2>", "<specific pro 3>", ...],
  "cons": ["<specific con 1>", "<specific con 2>", "<specific con 3>", ...],
  "themes": ["<theme 1>", "<theme 2>", "<theme 3>", ...],
  "insights": "<category-specific insights about this {category} based on the reviews>",
  "confidence": <0.0-1.0 confidence score based on review quantity and consistency>
}}"""
        
        return prompt
    
    def parse_response(self, response_text: str) -> Dict:
        """
        Parse Gemini's response to extract structured sentiment data
        
        Args:
            response_text: Raw response from Gemini
        
        Returns:
            Parsed sentiment data dict
        """
        try:
            # Clean the response
            cleaned = response_text.strip()
            
            # Remove markdown code blocks if present
            if '```json' in cleaned:
                cleaned = cleaned.split('```json')[1].split('```')[0].strip()
            elif '```' in cleaned:
                cleaned = cleaned.split('```')[1].split('```')[0].strip()
            
            # Find JSON in response
            json_start = cleaned.find('{')
            json_end = cleaned.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = cleaned[json_start:json_end]
                parsed = json.loads(json_str)
                
                # Validate structure
                required_fields = ['summary', 'pros', 'cons', 'themes', 'insights']
                for field in required_fields:
                    if field not in parsed:
                        raise ValueError(f"Missing required field: {field}")
                
                # Ensure lists are lists
                for field in ['pros', 'cons', 'themes']:
                    if not isinstance(parsed[field], list):
                        parsed[field] = []
                
                # Ensure confidence is float between 0 and 1
                if 'confidence' in parsed:
                    parsed['confidence'] = max(0.0, min(1.0, float(parsed['confidence'])))
                else:
                    parsed['confidence'] = 0.5
                
                return parsed
            
            raise ValueError("No valid JSON found in response")
            
        except Exception as e:
            print(f"Error parsing response: {e}")
            print(f"Raw response: {response_text[:500]}...")
            
            # Return default structure
            return {
                'summary': 'Unable to analyze reviews',
                'pros': [],
                'cons': [],
                'themes': [],
                'insights': 'Analysis failed',
                'confidence': 0.0,
                'error': str(e)
            }
    
    async def analyze_reviews(self, reviews: List[Dict], product_name: str, category: str = "product") -> Dict:
        """
        Analyze reviews using Gemini
        
        Args:
            reviews: List of review dicts from scraper
            product_name: Name of the product being reviewed
            category: Product category for context
        
        Returns:
            Sentiment analysis results
        """
        if not reviews:
            return {
                'summary': 'No reviews available to analyze',
                'pros': [],
                'cons': [],
                'themes': [],
                'insights': 'No insights available',
                'confidence': 0.0
            }
        
        # Build prompt
        prompt = self.build_analysis_prompt(reviews, product_name, category)
        
        try:
            # Generate response
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,  # Low temperature for consistent analysis
                    max_output_tokens=1000,
                )
            )
            
            # Parse response
            sentiment = self.parse_response(response.text)
            
            # Add metadata
            sentiment['reviews_analyzed'] = len(reviews[:50])  # We only analyze first 50
            sentiment['average_rating'] = sum(r['rating'] for r in reviews) / len(reviews) if reviews else 0
            
            return sentiment
            
        except Exception as e:
            print(f"Gemini API error: {e}")
            return {
                'summary': 'Failed to analyze reviews',
                'pros': [],
                'cons': [],
                'themes': [],
                'insights': 'Analysis unavailable',
                'confidence': 0.0,
                'error': str(e),
                'reviews_analyzed': len(reviews),
                'average_rating': sum(r['rating'] for r in reviews) / len(reviews) if reviews else 0
            }


async def main():
    """Test the sentiment analyzer"""
    import argparse
    import asyncio
    from ao_review_scraper import scrape_all_reviews
    
    parser = argparse.ArgumentParser(description='Analyze sentiment from AO.com reviews')
    parser.add_argument('product_url', help='Product page URL')
    parser.add_argument('--product-name', default='Product', help='Product name for context')
    parser.add_argument('--category', default='appliance', help='Product category')
    parser.add_argument('--output', '-o', help='Output JSON file')
    
    args = parser.parse_args()
    
    print(f"Scraping reviews from: {args.product_url}")
    
    # Scrape reviews first
    reviews_data = await scrape_all_reviews(args.product_url, max_pages=3)
    print(f"Scraped {reviews_data['total_scraped']} reviews")
    
    if not reviews_data['reviews']:
        print("No reviews found to analyze")
        return
    
    # Analyze sentiment
    print("\nAnalyzing sentiment with Gemini...")
    analyzer = SentimentAnalyzer()
    
    sentiment = await analyzer.analyze_reviews(
        reviews_data['reviews'],
        args.product_name,
        args.category
    )
    
    # Display results
    print("\n=== SENTIMENT ANALYSIS ===")
    print(f"Summary: {sentiment['summary']}")
    print(f"Confidence: {sentiment.get('confidence', 0):.2f}")
    print(f"Average Rating: {sentiment.get('average_rating', 0):.1f}/5")
    
    print("\nPROS:")
    for pro in sentiment['pros']:
        print(f"  ✓ {pro}")
    
    print("\nCONS:")
    for con in sentiment['cons']:
        print(f"  ✗ {con}")
    
    print("\nKEY THEMES:")
    for theme in sentiment['themes']:
        print(f"  • {theme}")
    
    print(f"\nINSIGHTS: {sentiment['insights']}")
    
    # Save if requested
    if args.output:
        output_data = {
            'product_url': args.product_url,
            'reviews': reviews_data,
            'sentiment': sentiment
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to: {args.output}")


if __name__ == '__main__':
    asyncio.run(main())