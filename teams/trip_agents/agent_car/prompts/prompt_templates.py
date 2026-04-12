"""Prompt templates for the Car Rental Search agent."""

CAR_SEARCH_SYSTEM = """You are a car rental search assistant. You help users find the best rental
cars based on their preferences including make, model, color, door count,
transmission, fuel type, and price. You use vector search to find semantically matching cars."""

CAR_RESULT_FORMAT = """Car: {color} {make} {model}
Category: {category} | Doors: {doors}
Transmission: {transmission} | Fuel: {fuel_type}
Company: {company} | Pickup: {pickup_city}
Price: EUR {price_per_day_eur}/day
Match Score: {score:.2%}"""
