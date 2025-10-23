"""
PDF-based specification extraction module.
"""

from .pdf_enricher import enrich_pdf_phase, calculate_enrichment_target, get_enrichment_gap

__all__ = ['enrich_pdf_phase', 'calculate_enrichment_target', 'get_enrichment_gap']
