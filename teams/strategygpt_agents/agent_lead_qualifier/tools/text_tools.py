"""Text processing tools for the Lead Qualifier agent."""

from langchain_core.tools import tool


@tool
def format_business_info(name: str, category: str, city: str, rating: float) -> str:
    """Format business information into a readable summary for script generation."""
    return (
        f"{name} is a {category} located in {city} "
        f"with a Google Maps rating of {rating:.1f}/5."
    )
