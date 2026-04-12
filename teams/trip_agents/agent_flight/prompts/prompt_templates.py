"""Prompt templates for the Flight Search agent."""

FLIGHT_SEARCH_SYSTEM = """You are a flight search assistant. You help users find the best flights
based on their preferences including airline, price, departure time, origin, destination,
and travel class. You use vector search to find semantically matching flights."""

FLIGHT_RESULT_FORMAT = """Flight: {airline} {flight_number}
Route: {origin_city} ({origin}) -> {destination_city} ({destination})
Date: {date} | Departure: {departure_time} | Arrival: {arrival_time}
Duration: {duration_minutes} min | Stops: {stops}
Class: {travel_class} | Price: EUR {price_eur}
Match Score: {score:.2%}"""
