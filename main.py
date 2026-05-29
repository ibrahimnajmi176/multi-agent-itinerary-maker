"""
=============================================================================
  MULTI-AGENT TRAVEL ITINERARY MAKER
  Assignment Part 1 — DeepLearning.AI Agentic AI Course
  All 4 Design Patterns Implemented:
    [1] PLANNING       → PlannerAgent
    [2] TOOL USE       → ResearchAgent (Wikipedia Free API)
    [3] REFLECTION     → CriticAgent (self-correction loop)
    [4] MULTI-AGENT    → Orchestrated by main()
=============================================================================
  Requirements:
    pip install groq requests
    export GROQ_API_KEY="your_key_here"
=============================================================================
"""

import os
import json
import time
import requests
from groq import Groq

# ── SETUP ──────────────────────────────────────────────────────────────────
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL  = "llama3-70b-8192"

# ANSI colour helpers (no extra deps)
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    CYAN   = "\033[96m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    BLUE   = "\033[94m"
    PURPLE = "\033[95m"
    DIM    = "\033[2m"

def banner(text, color=C.CYAN):
    width = 60
    print(f"\n{color}{C.BOLD}{'─' * width}")
    print(f"  {text}")
    print(f"{'─' * width}{C.RESET}")

def log(agent, message, color=C.DIM):
    print(f"  {color}[{agent}]{C.RESET} {message}")


# =============================================================================
# CORE LLM HELPER
# =============================================================================
def call_llm(system_prompt: str, user_message: str, require_json: bool = False) -> dict | str:
    """
    Central LLM call function used by every agent.
    - require_json=True  → uses response_format JSON mode + low temperature (0.2)
    - require_json=False → creative text mode with temperature 0.75
    """
    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_message},
    ]
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.2 if require_json else 0.75,
        response_format={"type": "json_object"} if require_json else None,
        max_tokens=2048,
    )
    content = response.choices[0].message.content
    if require_json:
        return json.loads(content)
    return content


# =============================================================================
# PATTERN 2 — TOOL USE
# Wikipedia Free API Tools (no key required)
# =============================================================================

def tool_wikipedia_search(query: str, results: int = 3) -> list[dict]:
    """
    Tool: Search Wikipedia for a query.
    Returns top N results with title + snippet.
    Wikipedia Action API — completely free, no auth needed.
    """
    url    = "https://en.wikipedia.org/w/api.php"
    params = {
        "action":   "query",
        "list":     "search",
        "srsearch": query,
        "srlimit":  results,
        "utf8":     "",
        "format":   "json",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        hits = data.get("query", {}).get("search", [])
        cleaned = []
        for h in hits:
            snippet = (h.get("snippet", "")
                       .replace('<span class="searchmatch">', "")
                       .replace("</span>", "")
                       .replace("&quot;", '"')
                       .replace("&#039;", "'"))
            cleaned.append({"title": h["title"], "snippet": snippet})
        return cleaned
    except Exception as e:
        return [{"title": "Error", "snippet": str(e)}]


def tool_wikipedia_summary(page_title: str) -> str:
    """
    Tool: Fetch the full introduction summary of a Wikipedia page.
    Uses the Wikipedia REST API — free, no auth needed.
    Returns a clean paragraph of text.
    """
    safe_title = page_title.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "ItineraryAgent/1.0"})
        if resp.status_code == 200:
            data = resp.json()
            return data.get("extract", "No summary available.")
        return f"Could not retrieve summary for '{page_title}' (status {resp.status_code})."
    except Exception as e:
        return f"Summary fetch failed: {str(e)}"


# =============================================================================
# PATTERN 1 — PLANNING
# PlannerAgent: Breaks destination + trip params into a structured research plan
# =============================================================================

def planner_agent(destination: str, days: int, interests: str) -> dict:
    """
    PATTERN 1 — PLANNING
    Analyses the trip parameters and generates:
      - A list of research topics (attractions, food, transport, culture)
      - A skeleton day-by-day structure
    Output is strict JSON for downstream agents to consume.
    """
    banner("PLANNER AGENT  [Pattern 1: Planning]", C.BLUE)
    log("Planner", "Analysing destination and generating research plan...")

    system = """You are a professional travel planning agent. 
Your job is to create a structured research plan for a trip itinerary.
You MUST respond with valid JSON only. No preamble, no explanation outside JSON.

Return a JSON object with exactly these keys:
{
  "destination_overview": "1 sentence about the destination",
  "research_topics": [
    "specific attraction or area to research",
    ...
  ],
  "day_themes": [
    "Day 1 theme (e.g. Arrival & Old City)",
    ...
  ],
  "food_queries": [
    "local dish or restaurant type to research",
    ...
  ],
  "transport_query": "how to get around in <destination>"
}

Rules:
- research_topics must have exactly 6 items (top attractions/areas)
- day_themes must have one entry per day
- food_queries must have 3 items
- Keep all strings concise (under 60 chars)"""

    user = f"""Destination: {destination}
Trip Duration: {days} day(s)
Traveller Interests: {interests}

Generate a research plan for this trip."""

    result = call_llm(system, user, require_json=True)

    log("Planner", f"Research plan created: {len(result.get('research_topics', []))} topics, "
                   f"{len(result.get('day_themes', []))} day themes")
    return result


# =============================================================================
# PATTERN 2 — TOOL USE (Research Agent)
# ResearchAgent: Executes the plan using Wikipedia tools
# =============================================================================

def research_agent(plan: dict, destination: str) -> dict:
    """
    PATTERN 2 — TOOL USE
    Uses Wikipedia Search and Summary tools to gather real data on:
      - Each attraction/area from the plan
      - Local food
      - Transport options
    Builds a rich research dataset for the writer agent.
    """
    banner("RESEARCH AGENT  [Pattern 2: Tool Use]", C.PURPLE)
    research_data = {
        "destination": destination,
        "attractions": {},
        "food":        {},
        "transport":   "",
        "overview":    "",
    }

    # ── 1. Destination Overview ──────────────────────────────────────────────
    log("Research", f"Fetching overview for '{destination}'...")
    overview_hits = tool_wikipedia_search(destination, results=1)
    if overview_hits:
        best_title = overview_hits[0]["title"]
        research_data["overview"] = tool_wikipedia_summary(best_title)
        log("Research", f"  ✓ Overview fetched from '{best_title}'")
    time.sleep(0.3)  # polite rate limiting

    # ── 2. Attractions ───────────────────────────────────────────────────────
    for topic in plan.get("research_topics", []):
        query = f"{topic} {destination}"
        log("Research", f"Searching: '{query}'")
        hits = tool_wikipedia_search(query, results=2)
        if hits:
            best = hits[0]
            summary = tool_wikipedia_summary(best["title"])
            # Keep only first 2 sentences for brevity
            sentences = summary.split(". ")
            short = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else summary
            research_data["attractions"][topic] = {
                "title":   best["title"],
                "summary": short,
            }
            log("Research", f"  ✓ Found: '{best['title']}'")
        time.sleep(0.3)

    # ── 3. Food ──────────────────────────────────────────────────────────────
    for food_q in plan.get("food_queries", []):
        query = f"{food_q} {destination} food"
        log("Research", f"Searching food: '{food_q}'")
        hits = tool_wikipedia_search(query, results=1)
        if hits:
            best = hits[0]
            summary = tool_wikipedia_summary(best["title"])
            sentences = summary.split(". ")
            short = ". ".join(sentences[:2]) + "." if len(sentences) > 1 else summary
            research_data["food"][food_q] = {
                "title":   best["title"],
                "summary": short,
            }
            log("Research", f"  ✓ Food found: '{best['title']}'")
        time.sleep(0.3)

    # ── 4. Transport ─────────────────────────────────────────────────────────
    transport_q = plan.get("transport_query", f"public transport {destination}")
    log("Research", f"Searching transport: '{transport_q}'")
    t_hits = tool_wikipedia_search(transport_q, results=1)
    if t_hits:
        t_summary = tool_wikipedia_summary(t_hits[0]["title"])
        sentences  = t_summary.split(". ")
        research_data["transport"] = ". ".join(sentences[:2]) + "."
        log("Research", f"  ✓ Transport info fetched")
    time.sleep(0.3)

    log("Research", f"Research complete — {len(research_data['attractions'])} attractions, "
                    f"{len(research_data['food'])} food entries")
    return research_data


# =============================================================================
# WRITER AGENT
# Drafts the full day-by-day itinerary from research data
# =============================================================================

def writer_agent(destination: str, days: int, plan: dict,
                 research_data: dict, feedback: str = None) -> str:
    """
    WRITER AGENT
    Turns the research dataset into a polished, day-by-day travel itinerary.
    If 'feedback' is provided (from CriticAgent), this is a revision pass.
    """
    if feedback:
        banner("WRITER AGENT  [Revision Pass]", C.GREEN)
        log("Writer", "Incorporating critic feedback into revised draft...")
    else:
        banner("WRITER AGENT  [First Draft]", C.GREEN)
        log("Writer", "Drafting itinerary from research data...")

    system = """You are an expert travel writer who creates vivid, practical travel itineraries.
Write in a warm, enthusiastic tone that inspires the reader.
Structure your output clearly with Day headers (Day 1, Day 2, etc.).

Each day must include:
- Morning activity (with brief description of why it's worth visiting)
- Afternoon activity
- Evening recommendation (dinner spot or local experience)
- 1 practical tip (transport, timing, cost, or etiquette)

End the itinerary with a short "Essential Tips" section (3 bullet points).
Use only the research data provided — do not invent specific facts."""

    research_json = json.dumps(research_data, indent=2)
    day_themes     = "\n".join([f"  {i+1}. {t}" for i, t in enumerate(plan.get("day_themes", []))])

    user = f"""Destination:     {destination}
Duration:        {days} day(s)
Planned Themes:
{day_themes}

Research Data (Wikipedia):
{research_json}
"""
    if feedback:
        user += f"\n\n--- CRITIC FEEDBACK TO ADDRESS ---\n{feedback}\n"
        user += "\nPlease rewrite the full itinerary addressing all points above."

    draft = call_llm(system, user, require_json=False)
    log("Writer", "Draft complete.")
    return draft


# =============================================================================
# PATTERN 3 — REFLECTION
# CriticAgent: Evaluates the itinerary and triggers self-correction
# =============================================================================

def critic_agent(draft: str, destination: str, days: int) -> dict:
    """
    PATTERN 3 — REFLECTION
    Reviews the itinerary draft on 5 criteria:
      1. Structure (does it cover all days?)
      2. Practicality (are activities doable in sequence?)
      3. Variety (mix of culture, food, leisure?)
      4. Research use (does it reference real Wikipedia facts?)
      5. Tone (is it engaging and clear?)

    Returns: {"score": int, "feedback": str, "strengths": str}
    Score >= 8 → accepted; < 8 → writer rewrites using feedback.
    """
    banner("CRITIC AGENT  [Pattern 3: Reflection]", C.YELLOW)
    log("Critic", "Evaluating draft itinerary...")

    system = """You are a strict travel editor evaluating a draft itinerary.
Score the itinerary on a scale of 1–10 based on:
1. Structure: clear day-by-day format, morning/afternoon/evening covered
2. Practicality: logical flow, timing, transport considered
3. Variety: mix of sightseeing, food, culture, and leisure
4. Specificity: uses real place names and facts (not vague generics)
5. Engagement: warm, inspiring tone that motivates travel

You MUST respond with valid JSON only using exactly these keys:
{
  "score": <integer 1-10>,
  "strengths": "<what is done well in 1-2 sentences>",
  "feedback": "<specific, actionable improvements needed — be detailed if score < 8>"
}"""

    user = f"""Destination: {destination} | Duration: {days} days

ITINERARY DRAFT:
{draft}

Evaluate this itinerary strictly and return JSON."""

    result = call_llm(system, user, require_json=True)
    score    = result.get("score", 0)
    feedback = result.get("feedback", "")
    strength = result.get("strengths", "")

    color = C.GREEN if score >= 8 else C.RED
    log("Critic", f"Score: {color}{C.BOLD}{score}/10{C.RESET}")
    log("Critic", f"Strengths: {strength}")
    if score < 8:
        log("Critic", f"Feedback: {C.YELLOW}{feedback}{C.RESET}")

    return result


# =============================================================================
# PATTERN 4 — MULTI-AGENT ORCHESTRATOR
# main() coordinates all agents in sequence with the reflection loop
# =============================================================================

def main():
    banner("MULTI-AGENT TRAVEL ITINERARY MAKER", C.CYAN)
    print(f"  {C.DIM}Implements all 4 Agentic Design Patterns{C.RESET}")
    print(f"  {C.DIM}Research powered by Wikipedia Free API{C.RESET}")
    print(f"  {C.DIM}LLM: Groq  |  Model: {MODEL}{C.RESET}\n")

    # ── INPUT ────────────────────────────────────────────────────────────────
    print(f"{C.BOLD}Enter trip details:{C.RESET}")
    destination = input("  Destination (e.g. Tokyo, Istanbul, Lahore): ").strip()
    while True:
        try:
            days = int(input("  Number of days (1–7):                      ").strip())
            if 1 <= days <= 7:
                break
            print("  Please enter a number between 1 and 7.")
        except ValueError:
            print("  Please enter a valid number.")
    interests = input("  Interests (e.g. history, food, nature, art): ").strip()
    if not interests:
        interests = "general sightseeing"

    print(f"\n{C.DIM}  Building itinerary for {days}-day trip to {destination}...{C.RESET}")

    # ── PHASE 1: PLANNING (Pattern 1) ────────────────────────────────────────
    plan = planner_agent(destination, days, interests)

    # ── PHASE 2: RESEARCH / TOOL USE (Pattern 2) ─────────────────────────────
    research_data = research_agent(plan, destination)

    # ── PHASE 3: WRITE FIRST DRAFT ───────────────────────────────────────────
    draft = writer_agent(destination, days, plan, research_data)

    # ── PHASE 4: REFLECTION + SELF-CORRECTION LOOP (Patterns 3 & 4) ─────────
    banner("REFLECTION LOOP  [Pattern 3 + Pattern 4]", C.CYAN)
    MAX_REVISIONS = 2

    for attempt in range(MAX_REVISIONS):
        log("Orchestrator", f"Revision cycle {attempt + 1}/{MAX_REVISIONS}")
        evaluation = critic_agent(draft, destination, days)
        score    = evaluation.get("score", 0)
        feedback = evaluation.get("feedback", "")

        if score >= 8:
            log("Orchestrator", f"{C.GREEN}Quality threshold met (score {score}/10). Finalising.{C.RESET}")
            break
        else:
            log("Orchestrator", f"{C.YELLOW}Score {score}/10 — requesting rewrite (attempt {attempt + 1}).{C.RESET}")
            draft = writer_agent(destination, days, plan, research_data, feedback=feedback)
    else:
        log("Orchestrator", f"{C.DIM}Max revisions reached. Using best available draft.{C.RESET}")

    # ── OUTPUT ───────────────────────────────────────────────────────────────
    banner("FINAL ITINERARY", C.GREEN)
    print(draft)

    filename = f"itinerary_{destination.lower().replace(' ', '_')}_{days}days.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"TRAVEL ITINERARY: {destination.upper()} — {days} DAYS\n")
        f.write(f"Generated by Multi-Agent Itinerary Maker\n")
        f.write(f"Research source: Wikipedia Free API\n")
        f.write("=" * 60 + "\n\n")
        f.write(draft)

    banner(f"Saved to '{filename}'", C.GREEN)
    print(f"\n  {C.DIM}Agents used: Planner → Researcher → Writer → Critic{C.RESET}")
    print(f"  {C.DIM}Patterns:    Planning | Tool Use | Reflection | Multi-Agent{C.RESET}\n")


if __name__ == "__main__":
    main()
