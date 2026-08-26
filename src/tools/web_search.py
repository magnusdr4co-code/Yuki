"""
Herramienta de búsqueda e inspección de corrientes culturales y noticias.
"""

from typing import List, Dict, Any
from .nous_portal import NousPortalClient

class WebSearchTool:
    def __init__(self, portal_client: NousPortalClient):
        self.portal = portal_client

    async def search_news_and_trends(self, topic: str) -> List[Dict[str, Any]]:
        """Realiza una búsqueda de tendencias a través de Firecrawl."""
        return await self.portal.search_trends_firecrawl(query=topic)
