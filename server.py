# server.py
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests

os.environ["SERPAPI_API_KEY"] = "fad53632c781136eff367f4946b563e90280c95996358844a610e584a45c1a61"

app = FastAPI()

# ========================= SEARCH TOOL =========================
class SearchQuery(BaseModel):
    q: str

@app.post("/search")
def search(query: SearchQuery):
    if "yahoo finance" not in query.q.lower():
        raise HTTPException(status_code=403, detail="Query must include 'Yahoo Finance' as source.")

    params = {
        "engine": "google",
        "q": query.q,
        "api_key": os.environ["SERPAPI_API_KEY"]
    }
    response = requests.get("https://serpapi.com/search", params=params)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.text)
    return response.json()

# ===================== PRICE RETURN TOOL =====================
class PriceReturnInput(BaseModel):
    initial_price: float
    final_price: float

@app.post("/price-return")
def calc_price_return(data: PriceReturnInput):
    return {"price_return": (data.final_price - data.initial_price) / data.initial_price * 100}

# ===================== DIVIDEND YIELD TOOL =====================
class DividendInput(BaseModel):
    dividend_total: float
    initial_price: float

@app.post("/dividend-yield")
def calc_dividend_yield(data: DividendInput):
    return {"dividend_yield": data.dividend_total / data.initial_price * 100}

# ===================== TOTAL RETURN TOOL =====================
class TotalReturnInput(BaseModel):
    price_return: float
    dividend_yield: float

@app.post("/total-return")
def calc_total_return(data: TotalReturnInput):
    return {"total_return": data.price_return + data.dividend_yield}

# ===================== COMPARISON TOOL =====================
class CompareInput(BaseModel):
    stock_a_name: str
    stock_a_return: float
    stock_b_name: str
    stock_b_return: float

@app.post("/compare")
def compare(data: CompareInput):
    diff = data.stock_a_return - data.stock_b_return
    winner = data.stock_a_name if diff > 0 else data.stock_b_name
    return {
        "summary": f"{winner} outperformed by {abs(diff):.2f}%. Total returns were: {data.stock_a_name} = {data.stock_a_return:.2f}%, {data.stock_b_name} = {data.stock_b_return:.2f}%."
    }
