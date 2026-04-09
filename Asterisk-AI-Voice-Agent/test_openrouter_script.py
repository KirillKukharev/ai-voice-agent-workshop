import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("Set OPENROUTER_API_KEY in the environment (never commit real keys).")
API_URL = "https://openrouter.ai/api/v1/chat/completions"

MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "minimax/minimax-m2.5:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "openai/gpt-oss-120b:free",
]

TEST_PROMPT = "Explain the concept of recursion in programming in 3-4 sentences."


def query_model(model: str, prompt: str) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "OpenRouter Latency Benchmark",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 256,
    }

    start = time.perf_counter()
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
        elapsed = time.perf_counter() - start

        if response.status_code != 200:
            return {
                "model": model,
                "success": False,
                "error": f"HTTP {response.status_code}: {response.json().get('error', {}).get('message', response.text)}",
                "latency": elapsed,
            }

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return {
            "model": model,
            "success": True,
            "content": content,
            "latency": elapsed,
            "prompt_tokens": usage.get("prompt_tokens", "?"),
            "completion_tokens": usage.get("completion_tokens", "?"),
            "total_tokens": usage.get("total_tokens", "?"),
        }

    except Exception as e:
        elapsed = time.perf_counter() - start
        return {
            "model": model,
            "success": False,
            "error": str(e),
            "latency": elapsed,
        }


def print_result(result: dict, rank: int = None):
    sep = "─" * 62
    model_label = result["model"]
    rank_str = f"#{rank}" if rank else ""
    print(f"\n┌{sep}┐")
    print(f"│ 🤖 {model_label:<56}{rank_str:>2} │")
    print(f"├{sep}┤")

    if result["success"]:
        latency_str = f"{result['latency']:.2f}s"
        tokens_str = (f"prompt={result['prompt_tokens']}  "
                      f"completion={result['completion_tokens']}  "
                      f"total={result['total_tokens']}")
        print(f"│ ⏱  Latency : {latency_str:<49}│")
        print(f"│ 📊 Tokens  : {tokens_str:<49}│")
        print(f"├{sep}┤")
        words = result["content"].split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 > 58:
                lines.append(current)
                current = w
            else:
                current = (current + " " + w).strip()
        if current:
            lines.append(current)
        for line in lines:
            print(f"│ {line:<60}│")
    else:
        print(f"│ ❌ Error   : {result['error']:<49}│")
        print(f"│ ⏱  Latency : {result['latency']:.2f}s{'':<46}│")

    print(f"└{sep}┘")


def main():
    print(f"\n{'═'*64}")
    print(f"  🏁  OpenRouter Latency Benchmark  —  {len(MODELS)} models")
    print(f"{'═'*64}")
    print(f"  Prompt: \"{TEST_PROMPT}\"")
    print(f"  Firing all requests in parallel...\n")

    results = []
    with ThreadPoolExecutor(max_workers=len(MODELS)) as executor:
        futures = {executor.submit(query_model, m, TEST_PROMPT): m for m in MODELS}
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda r: r["latency"])

    print("\n" + "═" * 64)
    print("  📋  Results  (sorted by latency, fastest → slowest)")
    print("═" * 64)

    for rank, result in enumerate(results, 1):
        print_result(result, rank)

    print(f"\n{'═'*64}")
    print(f"  🏆  Latency Summary")
    print(f"{'═'*64}")
    print(f"  {'Rank':<5} {'Model':<45} {'Latency':>8}  Status")
    print(f"  {'─'*4} {'─'*45} {'─'*8}  {'─'*7}")
    for rank, r in enumerate(results, 1):
        status = "✅ OK" if r["success"] else "❌ ERR"
        print(f"  #{rank:<4} {r['model']:<45} {r['latency']:>7.2f}s  {status}")

    fastest = next((r for r in results if r["success"]), None)
    slowest = next((r for r in reversed(results) if r["success"]), None)
    if fastest and slowest and fastest != slowest:
        diff = slowest["latency"] - fastest["latency"]
        print(f"\n  ⚡ Fastest : {fastest['model']}  ({fastest['latency']:.2f}s)")
        print(f"  🐢 Slowest : {slowest['model']}  ({slowest['latency']:.2f}s)")
        print(f"  📐 Delta   : {diff:.2f}s")

    print(f"\n{'═'*64}\n")


if __name__ == "__main__":
    main()