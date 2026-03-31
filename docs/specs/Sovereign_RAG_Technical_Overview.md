# Sovereign Local RAG Architecture
## A Technical Overview of the Offline Knowledge, Retrieval, and Self-Hosted Intelligence Stack

**Document Type:** Technical Article  
**Status:** Draft v1  
**Scope:** Formal overview of the architecture, data flow, components, strengths, bottlenecks, and future evolution of the sovereign local retrieval system

---

## Abstract

This document explains a self-hosted intelligence architecture designed to give a local AI the ability to search, read, ingest, organize, and reason over large offline and semi-offline knowledge stores without depending on centralized APIs, fixed training cutoffs, or closed hosted infrastructure.

The system combines:

- direct reading of offline Kiwix ZIM archives
- tool-calling / agentic retrieval
- local RSS and OPML-based ingestion
- persistent vector storage through ChromaDB
- local answer synthesis through Ollama
- multilingual source expansion
- self-ingestion of the system’s own architecture files

Taken together, these layers form a **sovereign local retrieval architecture** that is optimized for autonomy, transparency, and local control.

---

## 1. Introduction

Modern large language models are powerful, but in their raw form they have important limitations:

- they are bounded by training cutoff dates
- they often depend on centralized service providers
- they do not automatically know what local data is available
- they can only use external knowledge if that knowledge is either already embedded into the model or deliberately retrieved into context

This architecture addresses those limitations by shifting the problem away from “make the model know everything” and toward “give the model local tools, local memory, and local retrieval pathways.”

The result is not just a chatbot with a database.  
It is a layered knowledge system in which a local model can:

- search offline archives
- read documents on demand
- ingest fresh independent feeds
- retrieve semantically relevant knowledge
- answer from grounded local context
- inspect and explain its own operating structure

---

## 2. Architectural Goal

The central goal of the system is to establish a **sovereign local knowledge stack**.

In practical terms, this means:

- knowledge sources are stored or accessed locally
- the model can retrieve information dynamically
- ingestion is controlled by the operator
- source selection determines worldview coverage
- retrieval is inspectable
- updates happen on local schedules
- the AI is not dependent on a corporate hosted RAG system

This architecture treats the model as one layer inside a larger system rather than the sole container of intelligence.

---

## 3. Core Design Philosophy

The architecture is built on several core principles.

### 3.1 Do not preprocess everything if the model can read on demand
Massive corpora like full Wikipedia are too large to brute-force ingest casually.  
For those, direct archive search and selective reading is more efficient than embedding every page in advance.

### 3.2 Use the right retrieval path for the right corpus
Not all knowledge sources should be handled the same way.

- giant static archives benefit from tool-based direct reading
- constantly changing feeds benefit from chunking and vector storage
- system internals benefit from self-ingestion into local memory

### 3.3 Keep all major infrastructure local
The more of the stack that runs locally, the more control the operator has over:
- freshness
- worldview
- persistence
- privacy
- reproducibility

### 3.4 Source selection is upstream cognition
The OPML feed list is not just configuration.  
It is an upstream filter that shapes what the system can later retrieve and synthesize.

### 3.5 Retrieval should be transparent
The system should show which sources were retrieved so the operator can inspect evidence before trusting synthesis.

---

## 4. High-Level System Overview

The system is made of several cooperating layers:

```text
Offline ZIM Archives
  ↓
Tool-Based Search and Read

RSS / OPML Feed Ingestion
  ↓
HTML Cleaning
  ↓
Chronological JSONL Storage
  ↓
ChromaDB Vector Storage

Local LLM via Ollama
  ↓
Tool Calling / Semantic Retrieval
  ↓
Grounded Answer Synthesis

System Self-Ingestion
  ↓
Architecture-Aware Retrieval
```

These layers give the system four major knowledge paths:

1. **Direct archive reading**
2. **Semantic vector retrieval**
3. **Multilingual feed ingestion**
4. **Self-architecture retrieval**

---

## 5. Component 1: Offline Archive Access Through ZIM

The first major subsystem uses Kiwix ZIM archives as a local offline knowledge source.

A ZIM file can contain:
- offline encyclopedias
- Wikipedia mirrors
- domain-specific corpora such as WikiMed
- other prepackaged knowledge archives

The system connects to a ZIM archive using `libzim` and exposes two conceptual tools through a `ZimResearcher`-style class:

- a title/index search tool
- a document reading tool

### 5.1 Why this matters
Massive archives are expensive to fully preprocess.  
A simple direct-reading agent can instead:

1. search titles quickly
2. identify promising articles
3. open only the selected page
4. clean the HTML
5. answer from that exact content

This turns the AI into an active local researcher instead of a passive static text generator.

### 5.2 Benefits
- avoids multi-day brute-force ingestion
- makes giant archives usable immediately
- reads only relevant pages
- preserves local sovereignty over the corpus

### 5.3 Known bottlenecks
The baseline script design has two bottlenecks:
- single-threaded iteration
- slow HTML parsing with BeautifulSoup + `html.parser`

The text notes that this can be improved by:
- switching to `lxml`
- using multiprocessing
- building a faster title index for production use

---

## 6. Component 2: Agentic Tool-Calling Over the Offline Archive

The second layer connects the ZIM access tools to a local language model through Ollama.

Instead of requiring the model to already know the answer, the system lets the model:
- inspect available tools
- choose a tool call
- search the archive
- read a selected article
- continue reasoning after seeing the retrieved text

This is an **agentic RAG** pattern.

### 6.1 How the loop works

1. user asks a question
2. the model sees that tools are available
3. the model decides to call `search_index`
4. Python executes the search
5. results are returned to the model
6. the model chooses an exact title
7. the model calls `read_article`
8. Python reads and cleans the article
9. text is returned to the model
10. the model synthesizes a final answer

### 6.2 Why this is important
This allows very large offline libraries to be usable without full ingestion.  
The model only consumes compute where relevance is found.

---

## 7. Component 3: RSS / OPML Ingestion for Current Events and Ongoing Knowledge

The third subsystem handles constantly changing external information.

Instead of searching a giant static offline archive, this part of the architecture:
- reads an OPML file of feed sources
- fetches RSS or Atom items
- cleans article content
- stores the content locally by date
- pushes the content into a local vector database

### 7.1 Key outputs
This ingestion pipeline produces two forms of storage:

#### A. Chronological hard storage
The system writes articles into daily JSONL files such as:

```text
current_events_archive/events_YYYY-MM-DD.jsonl
```

This creates a local chronological archive.

#### B. Semantic vector storage
The same cleaned article text is stored in ChromaDB with metadata such as:
- date
- source
- title
- URL

This creates a semantic retrieval layer over the ingested event stream.

### 7.2 Deduplication
The ingestion system uses an MD5 hash of the article URL as a stable document ID.  
This allows repeated scheduled runs without duplicating articles already ingested.

### 7.3 Why this matters
This subsystem transforms current events into:
- searchable local memory
- date-organized hard storage
- semantic context that a local LLM can retrieve later

---

## 8. Component 4: Local Vector Retrieval Through ChromaDB

Once the feed ingestion pipeline populates the vector database, the local query engine can retrieve context semantically.

This query path works by:

1. connecting to a persistent ChromaDB collection
2. embedding the user query
3. retrieving the most relevant documents
4. printing the retrieved sources
5. building a strict grounded prompt
6. sending the prompt into a local Ollama model
7. streaming the answer back

### 8.1 Why this matters
This is how the system moves from raw stored text to grounded analysis.

### 8.2 Transparency
One of the strongest design choices is that the engine prints:
- retrieved titles
- dates
- sources

before the final answer is produced.

This makes the answer inspectable and helps prevent invisible retrieval bias.

### 8.3 Strict grounding
The prompt constrains the model to use only the provided context data.  
This reduces the chance that the model fills gaps from unrelated pretraining memory.

---

## 9. Component 5: Multilingual Feed Expansion

A major architectural feature is the use of a curated multilingual OPML file.

The feed matrix expands beyond English-only sources to include international and multilingual inputs, including examples from:
- French analysis
- Spanish academic or social-science material
- Norwegian and Danish archaeology
- German reporting
- broader non-US international broadcasting

### 9.1 Technical significance
This matters for three reasons:

#### A. Better primary-source proximity
Some fields publish their most useful material first in local languages.

#### B. Better worldview diversity
A multilingual corpus reduces dependence on one media ecosystem.

#### C. Better retrieval breadth
The vector store can hold signals from many regional or disciplinary vantage points, not just an Anglosphere one.

### 9.2 The OPML file as a worldview selector
The OPML configuration is not merely an import list.  
It is an upstream epistemic filter for the entire system.

---

## 10. Component 6: Self-Ingestion of the Architecture

One of the most interesting layers of the system is self-ingestion.

The design includes a script that reads the system’s own:
- Python source files
- dependency manifest
- OPML source configuration

and then ingests those files into the same or related ChromaDB memory.

### 10.1 Why this matters
This allows the local AI to answer questions about:
- how the ingestion pipeline works
- what dependencies the stack needs
- what sources are configured
- how the query engine is structured
- what files define the system

### 10.2 What this is technically
This is not mystical self-awareness.  
It is **retrieval-backed architectural introspection**.

The system can explain itself because its own files are part of the retrievable corpus.

---

## 11. Dependency Stack

The architecture described in the text uses a lightweight but capable local software stack.

Key components include:

- `libzim`
- `beautifulsoup4`
- `lxml`
- `feedparser`
- `chromadb`
- `ollama`
- `requests`

### 11.1 Functional mapping

| Dependency | Purpose |
|---|---|
| `libzim` | open and read ZIM archives |
| `beautifulsoup4` | clean article HTML into plain text |
| `lxml` | accelerate HTML parsing when needed |
| `feedparser` | parse RSS and Atom feeds |
| `chromadb` | persistent local vector storage |
| `ollama` | local LLM runtime and tool-calling interaction |
| `requests` | general network access for feed/article retrieval |

This is a relatively lean stack compared with cloud-first enterprise RAG systems.

---

## 12. Data Flow

## 12.1 Offline Archive Path

```text
User Question
  ↓
Ollama Agent
  ↓
search_index()
  ↓
title list
  ↓
read_article()
  ↓
cleaned article text
  ↓
grounded answer
```

---

## 12.2 Feed Ingestion Path

```text
OPML Feed List
  ↓
RSS / Atom Fetch
  ↓
HTML Cleaning
  ↓
JSONL Daily Archive
  ↓
ChromaDB Collection
```

---

## 12.3 Local Query Path

```text
User Question
  ↓
ChromaDB semantic query
  ↓
top relevant chunks
  ↓
strict grounded prompt
  ↓
Ollama synthesis
  ↓
final answer
```

---

## 12.4 Self-Architecture Path

```text
Source files + requirements + OPML
  ↓
self-ingestion script
  ↓
ChromaDB
  ↓
architecture-aware retrieval
  ↓
self-explanatory answer generation
```

---

## 13. Strengths of the Architecture

This design has several notable strengths.

### 13.1 Local sovereignty
The operator controls:
- storage
- ingestion timing
- model runtime
- feed sources
- retrieval corpus
- persistence

### 13.2 Efficient corpus handling
Large static corpora do not require immediate brute-force embedding.

### 13.3 Freshness
RSS and OPML ingestion allows the local knowledge base to stay updated on a schedule.

### 13.4 Transparency
The query system exposes retrieved sources before synthesis.

### 13.5 Extensibility
The architecture can be expanded by:
- adding new feeds
- adding new offline archives
- adding new self-ingested files
- adding new query or tool modes

### 13.6 Introspection
The AI can retrieve and explain its own architecture because the stack can ingest itself.

---

## 14. Bottlenecks and Constraints

The architecture is strong, but it is not without limits.

### 14.1 Slow direct archive search at scale
The baseline ZIM search design scans entries linearly.  
For very large archives, a dedicated title index would improve performance.

### 14.2 Parsing overhead
HTML cleaning remains a real cost, especially at scale.  
Moving from `html.parser` to `lxml` is a straightforward improvement.

### 14.3 Context-window limits
The local model still has a bounded context window.  
Long articles must be truncated or summarized before insertion into the prompt.

### 14.4 Mixed-corpus collection design
If current events, architecture files, and other corpora are stored in one vector collection, retrieval quality may eventually benefit from stricter collection separation.

### 14.5 Retrieval quality remains central
Strict grounding only works well if retrieval brings in the right material in the first place.

---

## 15. Operational Automation

The text also points toward running the ingestion system as a persistent local service using Linux `systemd`.

This matters because the architecture becomes much more valuable when it operates continuously.

### 15.1 Good automation targets
- current-events ingestion
- self-architecture ingestion
- periodic database maintenance
- archive refresh tasks
- scheduled backups

### 15.2 Why `systemd` matters
Compared with ad hoc scheduling, `systemd` offers:
- cleaner service control
- logging through the journal
- better restart behavior
- more reliable scheduling for background tasks

---

## 16. Recommended Structural Improvements

If the architecture were extended further, several upgrades would likely provide strong returns.

### 16.1 Build a dedicated ZIM title index
This would eliminate expensive repeated full entry scans.

### 16.2 Upgrade HTML cleaning path
Prefer:
- `lxml`
- faster content extraction
- optional boilerplate stripping

### 16.3 Separate vector collections by corpus type
Examples:
- `current_events`
- `system_architecture`
- `offline_reference`
- `multilingual_archaeology`

### 16.4 Add metadata-aware retrieval filters
Allow querying by:
- date
- source
- region
- language
- topic class

### 16.5 Add reranking
A lightweight reranker could improve top-k chunk quality before final prompt construction.

### 16.6 Add source trust or weighting logic
Not all feeds are equal.  
A weighting layer could influence retrieval ordering or synthesis confidence.

---

## 17. Technical Summary

The cleanest technical summary of the architecture is this:

> A self-hosted multi-layer retrieval system that combines offline ZIM archive reading, agentic tool-calling, scheduled multilingual feed ingestion, persistent local vector memory through ChromaDB, local LLM answer synthesis through Ollama, and self-ingestion of the system’s own code and configuration for architecture-aware retrieval.

That summary captures the system’s essential structure.

---

## 18. Why This Architecture Matters

What makes this architecture important is not any single script.  
It is the way the scripts fit together into a coherent strategy.

The system assumes that intelligence should not be trapped inside one model snapshot.  
Instead, it should emerge from:

- curated sources
- local storage
- retrieval discipline
- tool use
- inspectable synthesis
- architectural self-knowledge

This is a practical path toward local, autonomous, operator-controlled AI systems.

---

## 19. Conclusion

Sovereign Local RAG Architecture is best understood as a **local intelligence stack**, not a simple RAG demo.

It combines:
- direct archive reading for giant static corpora
- semantic retrieval for living information streams
- multilingual source expansion for broader coverage
- architecture self-ingestion for introspection
- local LLM synthesis for answer generation

Its real achievement is that it moves the center of gravity away from centralized model dependency and toward **local retrieval sovereignty**.

Instead of trying to make the model know everything in advance, it gives the model a disciplined way to go and get what it needs.

That is the core strength of the system.

---

## 20. Suggested Follow-On Documents

The most useful next documents to write would be:

1. **Data Flow Diagram Spec**
2. **Collection and Corpus Segmentation Plan**
3. **Metadata Schema for Feeds and Articles**
4. **Ollama Tool-Calling Integration Spec**
5. **Deployment Guide for Linux Background Services**
6. **Future Upgrades and Performance Roadmap**
