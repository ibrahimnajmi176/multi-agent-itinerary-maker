# Multi-Agent Travel Itinerary Maker
### Assignment Part 1 — DeepLearning.AI Agentic AI Course

A production-ready agentic application built in **raw Python** that generates
complete day-by-day travel itineraries using live Wikipedia data and a
self-correcting multi-agent pipeline.

---

## Design Patterns Implemented

| Pattern | Agent | What It Does |
|---|---|---|
| **1. Planning** | `planner_agent()` | Breaks destination + trip params into a structured JSON research plan — 6 attractions, day themes, food & transport queries |
| **2. Tool Use** | `research_agent()` | Calls Wikipedia Search API + Wikipedia REST Summary API (zero auth) to build a real research dataset |
| **3. Reflection** | `critic_agent()` | Scores the draft 1–10 on structure, practicality, variety, specificity, and tone. Triggers rewrites if score < 8 |
| **4. Multi-Agent** | `main()` orchestrator | Coordinates all 4 specialized agents in sequence with a self-correction loop |

---

## Architecture

```
User Input
    │
    ▼
[PlannerAgent]  ←── Pattern 1: Planning
    │  Outputs: research_topics, day_themes, food_queries
    ▼
[ResearchAgent] ←── Pattern 2: Tool Use (Wikipedia API)
    │  Outputs: attractions{}, food{}, transport, overview
    ▼
[WriterAgent]
    │  Outputs: draft itinerary
    ▼
[CriticAgent]   ←── Pattern 3: Reflection
    │  score < 8?  ──► [WriterAgent] (with feedback)
    │  score >= 8? ──► Finalise
    ▼
  essay.txt
```

---

## Setup

```bash
# 1. Install dependencies
pip install groq requests

# 2. Set your Groq API key (free at console.groq.com)
export GROQ_API_KEY="your_key_here"

# 3. Run
python main.py
```

---

## Example Run

```
Enter trip details:
  Destination: Istanbul
  Number of days: 3
  Interests: history, food, architecture

[Planner Agent]  Research plan created: 6 topics, 3 day themes
[Research Agent] Fetching overview for 'Istanbul'...
[Research Agent]   ✓ Overview fetched from 'Istanbul'
[Research Agent] Searching: 'Hagia Sophia Istanbul'
[Research Agent]   ✓ Found: 'Hagia Sophia'
...
[Critic Agent]   Score: 9/10
[Orchestrator]   Quality threshold met. Finalising.

Saved to 'itinerary_istanbul_3days.txt'
```

---

## Files

```
itinerary_agent/
├── main.py        # Full multi-agent system (single file, raw Python)
└── README.md
```

---

## APIs Used

| API | Auth | Docs |
|---|---|---|
| Wikipedia Action API (search) | None | https://www.mediawiki.org/wiki/API:Search |
| Wikipedia REST API (summary) | None | https://en.wikipedia.org/api/rest_v1/ |
| Groq Chat Completions | Free API key | https://console.groq.com |

---

## Notes
- No AI frameworks (no LangChain, no AutoGen) — raw Python as required
- Wikipedia APIs are completely free, no key or rate limit registration needed
- Groq free tier is sufficient for this workflow (~8 LLM calls per run)
- Max 2 revision cycles to control latency and cost
