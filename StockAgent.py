

import os, json, requests, re, litellm
from litellm import ModelResponse

# ─────────────────────────────────────────────────────────────
# Low‑level helpers
# ─────────────────────────────────────────────────────────────

SERP_KEY = os.getenv("SERPAPI_API_KEY")
if not SERP_KEY:
    raise RuntimeError("SERPAPI_API_KEY env‑var not set")

def serpapi_search(q: str, num_results: int = 10):
    try:
        params = {
            "engine": "google",
            "q": q,
            "api_key": SERP_KEY,
            "num": num_results,
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# Still use the MCP calculation micro‑endpoints
MCP_BASE = "http://localhost:8000"

def post_to_mcp(endpoint: str, data: dict):
    try:
        res = requests.post(f"{MCP_BASE}/{endpoint}", json=data, timeout=30)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────
# TOOL DEFINITIONS (OpenAI‑agents style)
# ─────────────────────────────────────────────────────────────

tools = [
    {
        "type": "function",
        "function": {
            "name": "search_stock_data",
            "description": "General SerpAPI (Google) search for any stock or dividend info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["query"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_price_return",
            "description": "Calculate price return from initial and final prices.",
            "parameters": {
                "type": "object",
                "properties": {
                    "initial_price": {"type": "number"},
                    "final_price": {"type": "number"},
                },
                "required": ["initial_price", "final_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_dividend_yield",
            "description": "Calculate dividend yield from total dividend and initial price.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dividend_total": {"type": "number"},
                    "initial_price": {"type": "number"},
                },
                "required": ["dividend_total", "initial_price"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_total_return",
            "description": "Calculate total return from price return and dividend yield.",
            "parameters": {
                "type": "object",
                "properties": {
                    "price_return": {"type": "number"},
                    "dividend_yield": {"type": "number"},
                },
                "required": ["price_return", "dividend_yield"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_returns",
            "description": "Compare total returns between two stocks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "stock_a_name": {"type": "string"},
                    "stock_a_return": {"type": "number"},
                    "stock_b_name": {"type": "string"},
                    "stock_b_return": {"type": "number"},
                },
                "required": ["stock_a_name", "stock_a_return", "stock_b_name", "stock_b_return"],
            },
        },
    },
]

# ─────────────────────────────────────────────────────────────
# TOOL EXECUTION WRAPPER
# ─────────────────────────────────────────────────────────────

def tool_handler(name: str, arguments: dict):
    dispatch = {
        "search_stock_data": lambda a: [serpapi_search(q) for q in a["query"]],
        "calculate_price_return": lambda a: post_to_mcp("price-return", a),
        "calculate_dividend_yield": lambda a: post_to_mcp("dividend-yield", a),
        "calculate_total_return": lambda a: post_to_mcp("total-return", a),
        "compare_returns": lambda a: post_to_mcp("compare", a),
    }
    return dispatch[name](arguments)

# ─────────────────────────────────────────────────────────────
# PARSER: Extract numbers from SerpAPI result
# ─────────────────────────────────────────────────────────────

def extract_price_or_dividend(result_json):
    texts = []
    for entry in result_json.get("organic_results", []):
        if "snippet" in entry:
            texts.append(entry["snippet"])
    full_text = " ".join(texts)
    matches = re.findall(r"\$([0-9]+(?:\.[0-9]{1,2})?)", full_text)
    return float(matches[0]) if matches else None

# ─────────────────────────────────────────────────────────────
# MAIN CALL — kicks everything off
# ─────────────────────────────────────────────────────────────

initial_prompts = [
    {
        "role": "system",
        "content": (
            "You are a meticulous financial‑analysis assistant. "
            "Use the available tools to gather data and compute total returns. "
            "Always respond with valid JSON when invoking a function. "
            "Never invent numbers; always cite tool output."
        ),
    },
    {
        "role": "user",
        "content": (
            "Compare total return (price + dividends) for AAPL vs MSFT over the past year.\n"
            "Start by searching for: \n"
            "1. AAPL stock price 1 year ago\n"
            "2. AAPL current stock price\n"
            "3. MSFT stock price 1 year ago\n"
            "4. MSFT current stock price\n"
            "5. AAPL dividends last 12 months\n"
            "6. MSFT dividends last 12 months\n"
        ),
    },
]

model_kwargs = {"format": "json"}

response: ModelResponse = litellm.completion(
    model="ollama/llama3",
    messages=initial_prompts,
    tools=tools,
    tool_choice="auto",
    stream=False,
    model_kwargs=model_kwargs,
)

calls = response.choices[0].message.tool_calls or []
if not calls:
    print("🤖 No tool calls made by the model.")
    print(response)
else:
    # Initialize vars
    aapl_init = aapl_final = msft_init = msft_final = None
    aapl_div = msft_div = None

    for idx, c in enumerate(calls):
        t_name = c.function.name
        t_args = json.loads(c.function.arguments)
        result = tool_handler(t_name, t_args)
        print(f"\n🛠️ {t_name} called with {t_args}")
        print("🔁 Result:", result)

        if t_name == "search_stock_data":
            for i, item in enumerate(result):
                val = extract_price_or_dividend(item)
                print(f"🔍 Parsed numeric value from search #{i+1}:", val)
                if i == 0: aapl_init = val
                elif i == 1: aapl_final = val
                elif i == 2: msft_init = val
                elif i == 3: msft_final = val
                elif i == 4: aapl_div = val
                elif i == 5: msft_div = val

    required = [aapl_init, aapl_final, msft_init, msft_final, aapl_div, msft_div]
    if not all(required):
        print("❌ Missing data — check search extraction above.")
        exit(1)

    aapl_price_ret = tool_handler("calculate_price_return", {
        "initial_price": aapl_init,
        "final_price": aapl_final,
    })["price_return"]

    aapl_div_yield = tool_handler("calculate_dividend_yield", {
        "dividend_total": aapl_div,
        "initial_price": aapl_init,
    })["dividend_yield"]

    aapl_total_return = tool_handler("calculate_total_return", {
        "price_return": aapl_price_ret,
        "dividend_yield": aapl_div_yield,
    })["total_return"]

    msft_price_ret = tool_handler("calculate_price_return", {
        "initial_price": msft_init,
        "final_price": msft_final,
    })["price_return"]

    msft_div_yield = tool_handler("calculate_dividend_yield", {
        "dividend_total": msft_div,
        "initial_price": msft_init,
    })["dividend_yield"]

    msft_total_return = tool_handler("calculate_total_return", {
        "price_return": msft_price_ret,
        "dividend_yield": msft_div_yield,
    })["total_return"]

    comparison_result = tool_handler("compare_returns", {
        "stock_a_name": "AAPL",
        "stock_a_return": aapl_total_return,
        "stock_b_name": "MSFT",
        "stock_b_return": msft_total_return,
    })

    print("\n📈 Final Comparison:")
    if isinstance(comparison_result, dict) and "result" in comparison_result:
        print("📈 Final Comparison:", comparison_result["result"])
    else:
        print("Success!:", comparison_result)

