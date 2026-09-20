"""
MCP server for the Travel Planning Assistant.

Exposes two tools over the Model Context Protocol:
  - get_weather_forecast: current/forecast weather for a destination (Open-Meteo, no API key)
  - convert_currency: currency conversion between two currencies (Frankfurter API, no API key)

Run standalone for testing:
    python -m src.mcp_server

Normally this file is launched as a subprocess by the LangChain agent (see agent.py),
which talks to it over stdio using the MCP protocol.
"""
import requests
from mcp.server.fastmcp import FastMCP

# Corporate networks frequently re-sign HTTPS traffic with an internal root CA that is
# installed in the OS certificate store but absent from the certifi bundle requests uses,
# which makes every outbound call fail with CERTIFICATE_VERIFY_FAILED. truststore routes
# verification through the OS store instead -- certificates are still fully verified.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:  # not installed: fall back to certifi, fine on unintercepted networks
    pass

mcp = FastMCP("travel-tools")


@mcp.tool()
def get_weather_forecast(destination: str, days: int = 3) -> dict:
    """
    Get the weather forecast for a destination city.

    Args:
        destination: City name, e.g. "Singapore".
        days: Number of forecast days to return (1-7).

    Returns:
        A dict with daily forecast entries (date, max/min temp in C, rain probability %),
        or an "error" key if the tool could not retrieve data.
    """
    days = max(1, min(days, 7))
    try:
        geo_resp = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": destination, "count": 1},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        results = geo_data.get("results")
        if not results:
            return {"error": f"Could not find location '{destination}'."}

        lat, lon = results[0]["latitude"], results[0]["longitude"]

        forecast_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto",
                "forecast_days": days,
            },
            timeout=10,
        )
        forecast_resp.raise_for_status()
        daily = forecast_resp.json().get("daily", {})

        forecast = []
        for i, date in enumerate(daily.get("time", [])):
            forecast.append(
                {
                    "date": date,
                    "temp_max_c": daily["temperature_2m_max"][i],
                    "temp_min_c": daily["temperature_2m_min"][i],
                    "rain_probability_pct": daily["precipitation_probability_max"][i],
                }
            )

        return {
            "destination": destination,
            "resolved_location": results[0].get("name", destination),
            "forecast": forecast,
            "source": "Open-Meteo API",
        }
    except requests.RequestException as e:
        return {"error": f"Weather service unavailable: {e}"}


@mcp.tool()
def convert_currency(amount: float, from_currency: str, to_currency: str) -> dict:
    """
    Convert an amount from one currency to another using current exchange rates.

    Args:
        amount: Amount to convert.
        from_currency: 3-letter source currency code, e.g. "INR".
        to_currency: 3-letter target currency code, e.g. "SGD".

    Returns:
        A dict with the converted amount and exchange rate used,
        or an "error" key if the tool could not retrieve data.
    """
    from_currency = from_currency.upper().strip()
    to_currency = to_currency.upper().strip()
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"amount": amount, "from": from_currency, "to": to_currency},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rate = data.get("rates", {}).get(to_currency)
        if rate is None:
            return {"error": f"Could not convert {from_currency} to {to_currency}."}

        return {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "converted_amount": rate,
            "rate_date": data.get("date"),
            "source": "Frankfurter API (European Central Bank reference rates)",
        }
    except requests.RequestException as e:
        return {"error": f"Currency conversion service unavailable: {e}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
