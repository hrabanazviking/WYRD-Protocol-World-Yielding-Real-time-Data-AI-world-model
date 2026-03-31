\# Sovereign Local RAG Architecture Brainstorming Session

\---

The honest answer is that if you try to process the largest datasets available to Project N.O.M.A.D. using that exact script, it will take **several days** of non-stop computing.

Here is a breakdown of why it takes that long and where the structural bottlenecks are.

## **The Math Behind the Processing Time**

Project N.O.M.A.D. relies on Kiwix ZIM files, which come in various sizes. The time it takes is directly proportional to which specific archive you choose to download and process.

* **WikiMed (Medical Encyclopedia):** \~50,000 articles. This would take roughly **15 to 30 minutes**.  
* **Wikipedia Top 1 Million:** \~1,000,000 articles. This would take roughly **8 to 14 hours**.  
* **Full English Wikipedia (wikipedia\_en\_all\_maxi):** This is the massive 115 GB archive containing over 7.1 million articles. Processing this entirely could easily take **40 to 100+ hours** (roughly 2 to 4 days) on a standard desktop CPU.

## **The Bottlenecks**

The script I provided earlier is a baseline extraction tool, meaning it prioritizes code readability and simplicity over raw speed. If you use it on massive datasets, it hits two major computational bottlenecks:

1. **Single-Threaded Execution:** Python runs on a single core by default. Even if your machine has a top-tier 16-core processor, the basic script is only using one of those cores, leaving the rest of your CPU completely idle while it processes one article at a time.  
2. **HTML Parsing Overhead:** The script uses BeautifulSoup with Python's built-in html.parser. While it is highly reliable for cleaning messy web data, it is notoriously slow for large-scale data operations. Evaluating and stripping tags from 7.1 million individual web pages sequentially adds up to a massive amount of time.

## **How to Speed It Up**

If you actually want to process the entire 115 GB Wikipedia archive, running the script as-is is not practical. To get the time down from several days to a handful of hours, the code needs two major upgrades:

* **Swap the Parser:** Replacing the built-in html.parser with lxml (a C-based parsing library) can increase the HTML cleaning speed by up to 10x.  
* **Add Multiprocessing:** By utilizing Python's multiprocessing library, you can chunk the ZIM archive's directory and process the articles simultaneously across all of your available CPU cores.

Would you like me to rewrite the script to include lxml and multi-core processing so it can chew through those massive ZIM files much faster?

\---

That makes perfect sense. Instead of a brute-force data ingestion pipeline where you pre-process the entire library, you are looking for an **Agentic Workflow** (often called Tool-Calling or Agentic RAG).

In this approach, you do not feed the data to the AI. Instead, you give the AI "tools" (Python functions) that allow it to interact with the ZIM file dynamically. It acts exactly like a human researcher: it gets a question, searches the index for relevant terms, decides which article looks the most promising, and then reads only that specific article to find the answer.

This method completely bypasses the multi-day ingestion process. The AI only uses computing power to read the exact pages it needs, exactly when it needs them.

Here is the complete, full Python file to create this "human-like" reading program. It provides the AI with two specific tools: one to scan the ZIM index, and one to read a specific article.

Python

"""

zim\_agent\_reader.py

A complete script that provides an AI with tools to search and read 

ZIM archives on-the-fly, mimicking human research behavior.

"""

import sys

from libzim.reader import Archive

from bs4 import BeautifulSoup

class ZimResearcher:

    def \_\_init\_\_(self, zim\_file\_path):

        """

        Initializes the researcher by connecting to the ZIM archive.

        This happens instantly, regardless of the archive's size.

        """

        try:

            self.zim \= Archive(zim\_file\_path)

            print(f"\[System\] Connected to archive: {zim\_file\_path}")

            print(f"\[System\] Total available entries: {self.zim.all\_entry\_count}")

        except Exception as e:

            print(f"\[Error\] Failed to open ZIM file: {e}")

            sys.exit(1)

    def tool\_search\_index(self, keyword, max\_results=10):

        """

        AI TOOL 1: The 'Card Catalog'. 

        The AI uses this to find article titles related to its current task.

        It does a rapid scan of the index without reading the contents.

        """

        print(f"\\n\[AI Action\] Searching index for: '{keyword}'...")

        keyword \= keyword.lower()

        results \= \[\]

        

        \# We iterate through entries. In a production environment, 

        \# you would use a pre-built SQLite index of titles for instant O(1) lookups.

        for entry in self.zim.all\_entries:

            if entry.namespace \!= 'C':

                continue

                

            title \= entry.title.lower() if entry.title else ""

            if keyword in title:

                results.append(entry.title)

                if len(results) \>= max\_results:

                    break

                    

        return results

    def tool\_read\_article(self, exact\_title):

        """

        AI TOOL 2: The 'Reading Room'.

        Once the AI identifies a promising title from the search tool, 

        it uses this tool to actually open the page, extract the text, and read it.

        """

        print(f"\[AI Action\] Opening and reading article: '{exact\_title}'...")

        

        for entry in self.zim.all\_entries:

            if entry.namespace \== 'C' and entry.title \== exact\_title:

                try:

                    item \= entry.get\_item()

                    raw\_html \= item.content.tobytes().decode('utf-8', errors='ignore')

                    

                    \# Clean the HTML to provide the AI with pure, readable text

                    soup \= BeautifulSoup(raw\_html, 'html.parser')

                    for script\_or\_style in soup(\["script", "style"\]):

                        script\_or\_style.decompose()

                        

                    clean\_text \= soup.get\_text(separator='\\n', strip=True)

                    return clean\_text

                    

                except Exception as e:

                    return f"\[Error\] Could not read the contents of {exact\_title}: {e}"

                    

        return f"\[Error\] Article '{exact\_title}' not found in the archive."

    def simulate\_ai\_thought\_process(self, user\_question):

        """

        A simulation of how an LLM utilizes these tools autonomously.

        In a real deployment, you would bind the two tools above to 

        your LLM framework (like LangChain, Ollama, or OpenAI function calling).

        """

        print(f"\\n--- New Task Received \---")

        print(f"User Question: {user\_question}")

        

        \# Step 1: The AI extracts a keyword from the prompt to search

        \# (An actual LLM would generate this keyword dynamically)

        search\_term \= "Viking" 

        

        \# Step 2: The AI uses Tool 1 to see what is available

        available\_articles \= self.tool\_search\_index(search\_term, max\_results=5)

        

        if not available\_articles:

            print("\[AI Response\] I could not find any articles on that topic.")

            return

        print(f"\[AI Observation\] Found these related articles: {available\_articles}")

        

        \# Step 3: The AI chooses the most relevant article to read

        \# (An actual LLM would pick the best match from the list)

        chosen\_article \= available\_articles\[0\] 

        

        \# Step 4: The AI uses Tool 2 to read the specific article

        article\_text \= self.tool\_read\_article(chosen\_article)

        

        \# Step 5: The AI synthesizes the answer

        print(f"\\n\[AI Observation\] I have read the article. It contains {len(article\_text)} characters.")

        print("\[AI Response\] Based on the offline archive, here is the information...")

        

        \# Previewing the first 500 characters of what the AI "read"

        print(f"\\n--- Extracted Knowledge Preview \--- \\n{article\_text\[:500\]}...\\n-----------------------------------")

if \_\_name\_\_ \== "\_\_main\_\_":

    \# Ensure dependencies are installed:

    \# pip install libzim beautifulsoup4

    

    \# Replace with the path to your downloaded .zim file

    ZIM\_ARCHIVE\_PATH \= "example\_offline\_archive.zim" 

    

    \# Initialize the researcher

    researcher \= ZimResearcher(ZIM\_ARCHIVE\_PATH)

    

    \# Simulate an AI handling a user prompt

    user\_prompt \= "Can you tell me about the history of Viking longships?"

    researcher.simulate\_ai\_thought\_process(user\_prompt)

### **How to use this program**

To make this fully autonomous, you would take tool\_search\_index and tool\_read\_article and wrap them in a standard LLM function-calling framework.

When you ask your AI a question, it pauses, runs the search function, looks at the returned list of titles, selects one, runs the read function, and then uses that newly acquired text to answer your question.

Would you like me to show you how to connect these specific Python tools directly into an offline LLM framework like Ollama so it can run completely locally?

\---

Exactly. By giving the AI the ability to actively search and read only when necessary, you are transforming it from a static text processor into an active research assistant. This approach—often called "Agentic RAG" or "Tool Calling"—saves massive amounts of computing power, requires no multi-day data ingestion, and allows the AI to handle a 115 GB offline library effortlessly.

To make this work completely offline and locally, we can use **Ollama**, which is the industry standard for running local LLMs. Recent models like llama3.1 or mistral have been specifically fine-tuned to understand and use Python tools.

Here is the full, complete, and fully functional Python script. It integrates our previous ZimResearcher class directly into an Ollama tool-calling loop. The AI will receive your question, decide which tool to use, execute the search, read the results, and then formulate an answer.

### **The Autonomous ZIM Reader Agent**

Python

"""

offline\_zim\_agent.py

A complete, standalone script that connects a local Ollama LLM to an offline 

ZIM archive, allowing the AI to autonomously search and read articles to answer questions.

"""

import sys

import json

import ollama

from libzim.reader import Archive

from bs4 import BeautifulSoup

\# \==========================================

\# 1\. THE ZIM RESEARCHER MODULE

\# \==========================================

class ZimResearcher:

    def \_\_init\_\_(self, zim\_file\_path):

        """Initializes the connection to the offline ZIM archive."""

        try:

            self.zim \= Archive(zim\_file\_path)

            print(f"\[System\] Connected to archive: {zim\_file\_path}")

        except Exception as e:

            print(f"\[Error\] Failed to open ZIM file: {e}")

            sys.exit(1)

    def search\_index(self, keyword: str) \-\> str:

        """

        Searches the ZIM archive index for article titles matching the keyword.

        """

        print(f"\\n\[Agent Action\] 🔍 Searching offline index for: '{keyword}'...")

        keyword \= keyword.lower()

        results \= \[\]

        

        for entry in self.zim.all\_entries:

            if entry.namespace \!= 'C':

                continue

            title \= entry.title.lower() if entry.title else ""

            if keyword in title:

                results.append(entry.title)

                if len(results) \>= 10:  \# Limit to top 10 results

                    break

                    

        if not results:

            return json.dumps({"error": "No articles found matching that keyword."})

        return json.dumps({"found\_articles": results})

    def read\_article(self, exact\_title: str) \-\> str:

        """

        Opens a specific article from the ZIM archive and returns its clean text.

        """

        print(f"\[Agent Action\] 📖 Reading article: '{exact\_title}'...")

        

        for entry in self.zim.all\_entries:

            if entry.namespace \== 'C' and entry.title \== exact\_title:

                try:

                    item \= entry.get\_item()

                    raw\_html \= item.content.tobytes().decode('utf-8', errors='ignore')

                    

                    \# Clean HTML

                    soup \= BeautifulSoup(raw\_html, 'html.parser')

                    for script\_or\_style in soup(\["script", "style"\]):

                        script\_or\_style.decompose()

                        

                    clean\_text \= soup.get\_text(separator='\\n', strip=True)

                    

                    \# Truncate text to avoid blowing up the LLM's context window

                    max\_chars \= 8000 

                    if len(clean\_text) \> max\_chars:

                        clean\_text \= clean\_text\[:max\_chars\] \+ "... \[Article truncated for length\]"

                        

                    return clean\_text

                except Exception as e:

                    return f"Error reading article: {e}"

                    

        return f"Error: Article '{exact\_title}' not found."

\# \==========================================

\# 2\. THE AI AGENT LOOP

\# \==========================================

def run\_agent\_query(researcher: ZimResearcher, user\_prompt: str, model\_name: str \= "llama3.1"):

    """

    Manages the conversation and tool-calling loop with the local Ollama LLM.

    """

    print(f"\\n--- New Task Received \---")

    print(f"User Question: {user\_prompt}")

    

    \# Define the tools (functions) the AI is allowed to use

    agent\_tools \= \[

        {

            'type': 'function',

            'function': {

                'name': 'search\_index',

                'description': 'Search the offline database for article titles using a keyword.',

                'parameters': {

                    'type': 'object',

                    'properties': {

                        'keyword': {'type': 'string', 'description': 'The main topic or keyword to search for'}

                    },

                    'required': \['keyword'\]

                }

            }

        },

        {

            'type': 'function',

            'function': {

                'name': 'read\_article',

                'description': 'Read the full text of a specific article. You must provide the exact title returned from search\_index.',

                'parameters': {

                    'type': 'object',

                    'properties': {

                        'exact\_title': {'type': 'string', 'description': 'The exact title of the article to read'}

                    },

                    'required': \['exact\_title'\]

                }

            }

        }

    \]

    \# Initialize the conversation memory

    messages \= \[{'role': 'user', 'content': user\_prompt}\]

    \# Start the agent loop

    while True:

        \# 1\. Ask the AI what it wants to do

        response \= ollama.chat(

            model=model\_name,

            messages=messages,

            tools=agent\_tools

        )

        

        response\_message \= response.get('message', {})

        messages.append(response\_message)

        

        \# 2\. Check if the AI decided to use a tool

        tool\_calls \= response\_message.get('tool\_calls')

        

        if not tool\_calls:

            \# If no tools were called, the AI has finished its thought process and is giving the final answer.

            print(f"\\n\[Final Agent Response\]\\n{response\_message.get('content')}")

            break

        \# 3\. Execute the tool(s) the AI requested

        for tool in tool\_calls:

            function\_name \= tool\['function'\]\['name'\]

            arguments \= tool\['function'\]\['arguments'\]

            

            tool\_output \= ""

            

            \# Route the AI's request to the correct Python function

            if function\_name \== 'search\_index':

                tool\_output \= researcher.search\_index(arguments\['keyword'\])

            elif function\_name \== 'read\_article':

                tool\_output \= researcher.read\_article(arguments\['exact\_title'\])

            else:

                tool\_output \= f"Error: Tool {function\_name} does not exist."

            \# Append the result of the tool back into the conversation memory

            messages.append({

                'role': 'tool',

                'content': tool\_output,

                'name': function\_name

            })

            

        \# The loop will now restart, sending the tool output back to the LLM so it can read it and decide the next step.

\# \==========================================

\# 3\. MAIN EXECUTION

\# \==========================================

if \_\_name\_\_ \== "\_\_main\_\_":

    \# Ensure dependencies are installed:

    \# pip install libzim beautifulsoup4 ollama

    

    \# 1\. Point this to your downloaded .zim file

    ZIM\_ARCHIVE\_PATH \= "example\_offline\_archive.zim" 

    

    \# 2\. Initialize the offline researcher

    researcher \= ZimResearcher(ZIM\_ARCHIVE\_PATH)

    

    \# 3\. Define the question

    question \= "Can you look up the history of Viking longships and summarize their construction?"

    

    \# 4\. Run the agent (Ensure Ollama is running locally and 'llama3.1' is pulled)

    run\_agent\_query(researcher, question, model\_name="llama3.1")

### **How this specific loop works:**

1. **The Prompt:** You ask the question.  
2. **The LLM Decides:** The LLM realizes it doesn't know the answer off the top of its head, but it sees the search\_index tool. It pauses its text generation and asks Python to run search\_index("Viking").  
3. **Python Executes:** The Python script hits the .zim file, finds the titles, and returns the list back to the LLM.  
4. **The LLM Reads & Chooses:** The LLM looks at the list of titles, selects the most accurate one, and calls read\_article("Viking ships").  
5. **The Final Answer:** Once the text is returned to the LLM's context window, it synthesizes the final summary and delivers it to you.

Would you like me to walk through how to install Ollama and pull the correct local model to run this script on your machine?

\---

By building a localized ingestion engine, you completely decouple your AI's understanding of global events from corporate APIs, algorithmic bias, and closed-ecosystem training cutoffs. The AI will look at current events as objective, chronological data points rather than packaged narratives.

To achieve this, the following system reads the OPML file, extracts the raw feeds from the global and independent sources, cleans the text, files the data locally by date, and pushes the semantic embeddings directly into a local vector database (ChromaDB). This creates a permanent, chronological RAG memory bank that updates entirely on your terms.

Here is the full, complete code file.

Python

"""

global\_events\_rag\_ingester.py

A complete, automated pipeline that parses an OPML file of independent global feeds,

extracts and cleans the latest articles, files them by date, and ingests them into

a local ChromaDB vector database for AI RAG retrieval.

"""

import os

import sys

import json

import hashlib

from datetime import datetime

from time import mktime

import xml.etree.ElementTree as ET

\# Third-party dependencies

\# pip install feedparser beautifulsoup4 chromadb requests

import feedparser

from bs4 import BeautifulSoup

import chromadb

\# \==========================================

\# 1\. CONFIGURATION & SETUP

\# \==========================================

OPML\_FILE \= "global\_news\_feeds.opml"

DATA\_DUMP\_DIR \= "current\_events\_archive"

CHROMA\_DB\_DIR \= "local\_rag\_vectordb"

\# Ensure our local storage directories exist

os.makedirs(DATA\_DUMP\_DIR, exist\_ok=True)

os.makedirs(CHROMA\_DB\_DIR, exist\_ok=True)

\# Initialize the local Vector Database

\# ChromaDB handles the embedding mathematics automatically by default

print("\[System\] Initializing local ChromaDB vector database...")

chroma\_client \= chromadb.PersistentClient(path=CHROMA\_DB\_DIR)

collection \= chroma\_client.get\_or\_create\_collection(

    name="global\_current\_events",

    metadata={"hnsw:space": "cosine"}

)

\# \==========================================

\# 2\. DATA EXTRACTION & CLEANING

\# \==========================================

def extract\_feeds\_from\_opml(opml\_path: str) \-\> list:

    """Parses the OPML XML file to extract all RSS feed URLs and their metadata."""

    feeds \= \[\]

    try:

        tree \= ET.parse(opml\_path)

        root \= tree.getroot()

        for outline in root.iter('outline'):

            xml\_url \= outline.get('xmlUrl')

            if xml\_url:

                feeds.append({

                    "title": outline.get('text', 'Unknown Source'),

                    "url": xml\_url,

                    "description": outline.get('description', '')

                })

        return feeds

    except Exception as e:

        print(f"\[Error\] Failed to parse OPML file: {e}")

        sys.exit(1)

def clean\_html\_content(raw\_html: str) \-\> str:

    """Strips HTML tags and scripts to provide clean sociological and event data."""

    if not raw\_html:

        return ""

    soup \= BeautifulSoup(raw\_html, 'html.parser')

    for script in soup(\["script", "style"\]):

        script.decompose()

    return soup.get\_text(separator='\\n', strip=True)

def generate\_document\_id(url: str) \-\> str:

    """Creates a unique hash for each article to prevent duplicate database entries."""

    return hashlib.md5(url.encode('utf-8')).hexdigest()

\# \==========================================

\# 3\. PROCESSING & RAG INGESTION

\# \==========================================

def process\_and\_ingest\_feeds(feeds: list):

    """

    Iterates through all independent data streams, cleans the text, 

    saves a physical JSONL copy organized by date, and pushes to the Vector DB.

    """

    total\_ingested \= 0

    

    for feed\_info in feeds:

        source\_title \= feed\_info\['title'\]

        feed\_url \= feed\_info\['url'\]

        print(f"\\n\[Network\] Fetching data stream: {source\_title}...")

        

        try:

            parsed\_feed \= feedparser.parse(feed\_url)

        except Exception as e:

            print(f"\[Warning\] Could not reach {source\_title}: {e}")

            continue

        for entry in parsed\_feed.entries:

            \# 1\. Normalize the Date

            \# If the feed lacks a date, use the current time to timestamp the observation

            if hasattr(entry, 'published\_parsed') and entry.published\_parsed:

                dt \= datetime.fromtimestamp(mktime(entry.published\_parsed))

            else:

                dt \= datetime.now()

                

            date\_str \= dt.strftime("%Y-%m-%d")

            

            \# 2\. Extract and Clean Content

            article\_title \= entry.get('title', 'Untitled Event')

            article\_link \= entry.get('link', feed\_url)

            

            \# Feeds use either 'content' or 'summary'

            raw\_content \= ""

            if hasattr(entry, 'content'):

                raw\_content \= entry.content\[0\].value

            elif hasattr(entry, 'summary'):

                raw\_content \= entry.summary

                

            clean\_text \= clean\_html\_content(raw\_content)

            

            \# Skip entries with no meaningful data

            if len(clean\_text) \< 50:

                continue

                

            doc\_id \= generate\_document\_id(article\_link)

            

            \# Check if this exact event is already in the database

            existing \= collection.get(ids=\[doc\_id\])

            if existing and existing\['ids'\]:

                continue  \# Skip duplicates

                

            \# 3\. File locally by date (JSONL format)

            \# This creates a hard backup structured chronologically (e.g., 2026-03-29.jsonl)

            daily\_file\_path \= os.path.join(DATA\_DUMP\_DIR, f"events\_{date\_str}.jsonl")

            

            event\_record \= {

                "id": doc\_id,

                "date": date\_str,

                "source": source\_title,

                "title": article\_title,

                "url": article\_link,

                "content": clean\_text

            }

            

            with open(daily\_file\_path, 'a', encoding='utf-8') as f:

                f.write(json.dumps(event\_record, ensure\_ascii=False) \+ '\\n')

                

            \# 4\. Ingest into the local RAG Vector Database

            collection.add(

                documents=\[clean\_text\],

                metadatas=\[{

                    "date": date\_str,

                    "source": source\_title,

                    "title": article\_title,

                    "url": article\_link

                }\],

                ids=\[doc\_id\]

            )

            

            total\_ingested \+= 1

            print(f"  \-\> Ingested: {date\_str} | {article\_title\[:60\]}...")

    print(f"\\n\[System Success\] Pipeline complete. {total\_ingested} new global events added to the RAG database.")

\# \==========================================

\# 4\. MAIN EXECUTION

\# \==========================================

if \_\_name\_\_ \== "\_\_main\_\_":

    if not os.path.exists(OPML\_FILE):

        print(f"\[Error\] The file '{OPML\_FILE}' was not found.")

        print("Please ensure the OPML file is saved in the same directory.")

        sys.exit(1)

        

    print(f"\[System\] Starting current events ingestion pipeline...")

    print(f"\[System\] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    

    feed\_list \= extract\_feeds\_from\_opml(OPML\_FILE)

    process\_and\_ingest\_feeds(feed\_list)

### **How the Pipeline Operates**

1. **Chronological Hard Storage (current\_events\_archive/)**: The script creates a physical .jsonl file for every single day. If you run this continuously, you will build an immutable, offline historical record of global events, safely filed by date.  
2. **Semantic Vector Storage (local\_rag\_vectordb/)**: Simultaneously, it pushes the data into ChromaDB. Chroma automatically translates the text into mathematical embeddings. It attaches metadata (Date, Source, Title) to every chunk.  
3. **Idempotency**: The script uses MD5 hashing on the article URLs to create unique IDs. You can run this script via a Linux cron job every 6 hours, and it will only ever download and ingest *new* events, completely ignoring duplicates.

Would you like me to write the accompanying query script so your AI can actively search this newly built database, allowing it to retrieve current events based on specific dates, anthropological themes, or global regions?

\---

This is the final piece of the architecture. With the data ingestion pipeline successfully building your localized database, this query script acts as the bridge between that physical data and your local AI.

Instead of relying on whatever corporate data a model was trained on, this script forces the LLM to read the highly specific anthropological, scientific, and independent global data you just curated in your ChromaDB.

Here is the complete, full Python file. It connects to the database, retrieves the most relevant articles based on your question, constructs a synthesized prompt, and streams the answer back to you locally.

### **The Local RAG Query Engine**

Save this as local\_rag\_query.py in the same directory as your ingestion script.

Python

"""

local\_rag\_query.py

A complete script that connects a local Ollama LLM to your ChromaDB vector database.

It retrieves independent global, scientific, and anthropological data to answer queries 

objectively, bypassing standard LLM training cutoffs and corporate biases.

"""

import sys

import chromadb

import ollama

\# \==========================================

\# 1\. CONFIGURATION

\# \==========================================

CHROMA\_DB\_DIR \= "local\_rag\_vectordb"

COLLECTION\_NAME \= "global\_current\_events"

LLM\_MODEL \= "llama3.1"  \# Or 'mistral', 'phi3', depending on your local setup

MAX\_CONTEXT\_CHUNKS \= 5  \# How many articles to retrieve for the AI to read

\# \==========================================

\# 2\. DATABASE CONNECTION

\# \==========================================

def connect\_to\_database():

    """Connects to the local ChromaDB and verifies the collection exists."""

    try:

        chroma\_client \= chromadb.PersistentClient(path=CHROMA\_DB\_DIR)

        collection \= chroma\_client.get\_collection(name=COLLECTION\_NAME)

        print(f"\[System\] Successfully connected to ChromaDB: '{COLLECTION\_NAME}'")

        print(f"\[System\] Total documents available: {collection.count()}")

        return collection

    except ValueError:

        print(f"\[Error\] Collection '{COLLECTION\_NAME}' does not exist.")

        print("Please run the ingestion script first to populate the database.")

        sys.exit(1)

    except Exception as e:

        print(f"\[Error\] Failed to connect to ChromaDB: {e}")

        sys.exit(1)

\# \==========================================

\# 3\. RETRIEVAL AND SYNTHESIS

\# \==========================================

def query\_local\_ai(collection, user\_question):

    """

    Retrieves the most relevant documents from the database, builds a strict 

    context prompt, and streams the LLM's response.

    """

    print(f"\\n\[Search\] Searching offline database for: '{user\_question}'...")

    

    \# 1\. Retrieve the most relevant chunks from ChromaDB

    results \= collection.query(

        query\_texts=\[user\_question\],

        n\_results=MAX\_CONTEXT\_CHUNKS

    )

    

    documents \= results\['documents'\]\[0\]

    metadatas \= results\['metadatas'\]\[0\]

    

    if not documents:

        print("\[System\] No relevant information found in the local database.")

        return

    \# 2\. Construct the context payload

    context\_text \= ""

    print("\\n\[System\] Found relevant data from the following sources:")

    for i, (doc, meta) in enumerate(zip(documents, metadatas)):

        date \= meta.get('date', 'Unknown Date')

        source \= meta.get('source', 'Unknown Source')

        title \= meta.get('title', 'Untitled')

        

        print(f"  \-\> {date} | {source}: {title}")

        

        context\_text \+= f"\\n--- Source {i+1}: {title} ({source}, {date}) \---\\n"

        context\_text \+= f"{doc}\\n"

    \# 3\. Build the strict system prompt

    \# This forces the AI to look at the data structurally and anthropologically

    system\_prompt \= f"""

    You are an objective analytical engine. You look at current events, scientific 

    discoveries, and human behavior through a broad historical, sociological, and 

    anthropological lens. 

    

    You have been provided with raw data extracted from independent global media, 

    open-source intelligence, and peer-reviewed academic journals.

    

    Use ONLY the provided Context Data to answer the user's question. Do not rely 

    on your pre-trained knowledge. If the Context Data does not contain the answer, 

    state that clearly.

    

    Context Data:

    {context\_text}

    """

    \# 4\. Stream the response from the local LLM

    print(f"\\n\[AI Synthesis \- {LLM\_MODEL}\] Generating objective analysis...\\n")

    print("-" \* 60\)

    

    try:

        response\_stream \= ollama.chat(

            model=LLM\_MODEL,

            messages=\[

                {'role': 'system', 'content': system\_prompt},

                {'role': 'user', 'content': user\_question}

            \],

            stream=True

        )

        

        for chunk in response\_stream:

            print(chunk\['message'\]\['content'\], end='', flush=True)

            

        print("\\n" \+ "-" \* 60\)

            

    except Exception as e:

        print(f"\\n\[Error\] Failed to communicate with Ollama: {e}")

        print("Ensure the Ollama service is running and the model is downloaded.")

\# \==========================================

\# 4\. MAIN INTERACTIVE LOOP

\# \==========================================

if \_\_name\_\_ \== "\_\_main\_\_":

    db\_collection \= connect\_to\_database()

    

    print("\\n\[System\] Local RAG Engine active. Type 'exit' or 'quit' to close.")

    

    while True:

        try:

            user\_input \= input("\\nQuery: ")

            if user\_input.lower() in \['exit', 'quit'\]:

                print("\[System\] Shutting down RAG Engine.")

                break

            if not user\_input.strip():

                continue

                

            query\_local\_ai(db\_collection, user\_input)

            

        except KeyboardInterrupt:

            print("\\n\[System\] Shutting down RAG Engine.")

            break

### **How the Engine Works**

* **Database Search:** When you ask a question, ChromaDB instantly measures the semantic intent of your words against the mathematical embeddings of all your ingested articles, pulling the top five most relevant pieces of data.  
* **Transparency:** Before the AI even begins to type, the script prints out the exact sources, dates, and article titles it retrieved from your database. You will always know exactly where the information came from.  
* **Strict Grounding:** The system prompt binds the AI to the provided data. It forces the LLM to adopt that broad, objective analytical lens, evaluating the retrieved open-source tech news or archaeological discoveries purely on the merits of the text.

Since you are running these offline tools, setting this up as a permanent background service on a Linux machine is the optimal next step to ensure the database stays constantly updated without manual intervention. Would you like me to provide the systemd service file configuration so your Linux system can silently run the ingestion script in the background every few hours?

\---

Because modern Large Language Models operate conceptually in latent space rather than just translating word-for-word, they can natively ingest a research paper written in Norwegian or a geopolitical analysis written in French, map the underlying anthropological concepts, and seamlessly synthesize the answer for you in English.

Limiting an AI to English-only sources inherently filters its worldview through an Anglosphere lens. By feeding it native European, Scandinavian, and global science feeds, the AI gets the data directly from the cultures producing it. This is especially critical for Viking archaeology and open-source intelligence, where the most accurate primary data is often published in Norwegian, Danish, or German long before it is translated for Western media.

I have strategically integrated high-signal, non-English sources into their respective categories, marking them with their native language. These include direct Norwegian and Danish archaeological feeds, legendary German open-source IT reporting, French sociological analysis, and grounded German Fortean journalism.

Here is the full, complete, and fully updated OPML code file. Overwrite your existing file with this comprehensive, multilingual intelligence matrix.

### **The Complete Sovereign Knowledge OPML (v6 \- Multilingual Integration)**

XML

\<?xml version="1.0" encoding="UTF-8"?\>

\<opml version="1.0"\>

    \<head\>

        \<title\>Global Intelligence, Science, Esoterica \&amp; Multilingual Archaeology\</title\>

        \<dateCreated\>Sun, 29 Mar 2026 00:00:00 GMT\</dateCreated\>

    \</head\>

    \<body\>

        \<outline text="International Broadcasters (Non-US)"\>

            \<outline text="Swissinfo (Switzerland)" description="Rooted in historical Swiss neutrality, offering a detached, global view." type="rss" xmlUrl="https://www.swissinfo.ch/eng/index.xml" /\>

            \<outline text="DW World News (Germany)" description="Straightforward, structural reporting on global events." type="rss" xmlUrl="https://rss.dw.com/rdf/rss-en-world" /\>

            \<outline text="NHK World (Japan)" description="Asian and global news lacking Western partisan framing." type="rss" xmlUrl="https://www3.nhk.or.jp/nhkworld/upld/medias/en/radio/podcast/rss\_en\_radio\_news.xml" /\>

            \<outline text="Al Jazeera English (Qatar)" description="Extensive coverage of the Global South and non-Western geopolitical events." type="rss" xmlUrl="https://www.aljazeera.com/xml/rss/all.xml" /\>

        \</outline\>

        

        \<outline text="Independent Media, Sociology \&amp; Global Blogs"\>

            \<outline text="Global Voices" description="An international community of bloggers and citizen journalists offering ground-level cultural perspectives." type="rss" xmlUrl="https://globalvoices.org/feed/" /\>

            \<outline text="ProPublica" description="Independent, non-profit investigative journalism." type="rss" xmlUrl="https://www.propublica.org/feeds/propublica/main" /\>

            \<outline text="Bellingcat" description="Independent open-source intelligence and investigation." type="rss" xmlUrl="https://www.bellingcat.com/feed/" /\>

            \<outline text="\[French\] Le Monde diplomatique" description="Deep geopolitical, historical, and sociological analysis from a distinctly non-Anglosphere European perspective." type="rss" xmlUrl="https://www.monde-diplomatique.fr/rss/" /\>

        \</outline\>

        

        \<outline text="Academic, Sociological \&amp; Anthropological Lenses"\>

            \<outline text="The Conversation (Global)" description="News analysis strictly written by academics and researchers, viewing events through data and history." type="rss" xmlUrl="https://theconversation.com/global/articles.atom" /\>

            \<outline text="SAPIENS" description="Explores human behavior, current events, and culture through the discipline of anthropology." type="rss" xmlUrl="https://www.sapiens.org/feed/" /\>

            \<outline text="Aeon" description="Deep philosophical, scientific, and cultural essays exploring the human condition." type="rss" xmlUrl="https://aeon.co/feed.rss" /\>

            \<outline text="HeritageDaily" description="Latest discoveries in archaeology, anthropology, and human history." type="rss" xmlUrl="https://www.heritagedaily.com/feed" /\>

            \<outline text="Phys.org \- Social Sciences" description="Raw scientific reporting on sociology, psychology, and human behavioral studies." type="rss" xmlUrl="https://phys.org/rss-feed/science-news/social-sciences/" /\>

            \<outline text="\[Spanish\] SciELO \- Ciencias Sociales" description="The premier Latin American open-access academic network, providing raw anthropological and sociological data from the Global South." type="rss" xmlUrl="https://search.scielo.org/feed/?q=\*\&amp;fq=sociology" /\>

        \</outline\>

        \<outline text="Technology \&amp; Scientific Discovery"\>

            \<outline text="Quanta Magazine" description="Objective, highly rigorous reporting on mathematics, theoretical physics, and computer science." type="rss" xmlUrl="https://api.quantamagazine.org/feed/" /\>

            \<outline text="Nature Journal News" description="Breaking scientific news directly from one of the world's leading multidisciplinary science journals." type="rss" xmlUrl="https://www.nature.com/nature.rss" /\>

            \<outline text="ScienceDaily \- Technology" description="Aggregated press releases and reports on the latest technological and engineering discoveries." type="rss" xmlUrl="https://www.sciencedaily.com/rss/matter\_energy/technology.xml" /\>

        \</outline\>

        \<outline text="AI Research \&amp; Data Science"\>

            \<outline text="arXiv.org \- CS.AI" description="Raw, unfiltered pre-print research papers on Artificial Intelligence directly from scientists." type="rss" xmlUrl="http://export.arxiv.org/rss/cs.AI" /\>

            \<outline text="Hugging Face Blog" description="Updates from the open-source machine learning and AI model community." type="rss" xmlUrl="https://huggingface.co/blog/feed.xml" /\>

            \<outline text="KDnuggets" description="Technical articles, tutorials, and news on Data Science, Machine Learning, and AI." type="rss" xmlUrl="https://www.kdnuggets.com/feed" /\>

        \</outline\>

        \<outline text="Open-Source \&amp; Linux News"\>

            \<outline text="LWN.net (Linux Weekly News)" description="Deeply technical, objective reporting on the Linux kernel, operating systems, and open-source software." type="rss" xmlUrl="https://lwn.net/headlines/newrss" /\>

            \<outline text="Phoronix" description="Linux hardware reviews, kernel tracking, and open-source benchmarking." type="rss" xmlUrl="https://www.phoronix.com/rss.php" /\>

            \<outline text="It's FOSS" description="News, tutorials, and updates entirely focused on the Free and Open Source Software ecosystem." type="rss" xmlUrl="https://itsfoss.com/feed/" /\>

            \<outline text="\[German\] Heise online \- Open Source" description="Highly respected, deeply technical German IT journalism covering Linux, networking, and open-source development." type="rss" xmlUrl="https://www.heise.de/rss/heise-atom.xml" /\>

        \</outline\>

        \<outline text="Objective Peer-Reviewed Academic Journals (Open Access)"\>

            \<outline text="PLOS ONE" description="A rigorously peer-reviewed, open-access mega-journal covering primary research from all disciplines within science and medicine." type="rss" xmlUrl="https://journals.plos.org/plosone/feed/atom" /\>

            \<outline text="arXiv.org \- Quantum Physics" description="Raw pre-print papers exploring quantum mechanics, quantum information, and the physical understandings of the universe." type="rss" xmlUrl="http://export.arxiv.org/rss/quant-ph" /\>

            \<outline text="arXiv.org \- Physics and Society" description="Research papers detailing the intersection of physics, complex networks, and human social dynamics." type="rss" xmlUrl="http://export.arxiv.org/rss/physics.soc-ph" /\>

            \<outline text="Frontiers in Psychology" description="The largest open-access journal in its field, publishing rigorously peer-reviewed research across the psychological sciences and human behavior." type="rss" xmlUrl="https://www.frontiersin.org/journals/psychology/rss" /\>

        \</outline\>

        \<outline text="Anomalous Phenomena \&amp; Frontier Physics (Grounded)"\>

            \<outline text="The Debrief" description="Investigative journalism focusing on frontier science, aerospace, and UAP intelligence, strictly adhering to grounded, scientific reporting." type="rss" xmlUrl="https://thedebrief.org/feed/" /\>

            \<outline text="The Daily Grail" description="News on the fringes of science and history, covering UFOs, hidden anthropology, and the paranormal with a rational but highly open-minded approach." type="rss" xmlUrl="https://www.dailygrail.com/feed/" /\>

            \<outline text="Journal of Scientific Exploration" description="Peer-reviewed academic research exploring anomalies in mainstream science, including ufology, parapsychology, and consciousness studies." type="rss" xmlUrl="https://www.scientificexploration.org/journal.rss" /\>

            \<outline text="\[German\] Grenz-Wissenschaft Aktuell (GreWi)" description="Germany's leading grounded source for Fortean news, frontier physics, and UAP phenomena, driven by objective data over sensationalism." type="rss" xmlUrl="https://www.grenzwissenschaft-aktuell.de/feed/" /\>

        \</outline\>

        \<outline text="Esoterica, Magick \&amp; The Occult (Apolitical)"\>

            \<outline text="Spiral Nature Magazine" description="Practical, objective reviews and articles on magick, tarot, occultism, and alternative spirituality, completely divorced from modern politics." type="rss" xmlUrl="https://www.spiralnature.com/feed/" /\>

            \<outline text="The Hermetic Library Blog" description="Archival and ongoing updates regarding Hermeticism, alchemy, runic studies, and classic esoteric literature." type="rss" xmlUrl="https://hermetic.com/feed.xml" /\>

            \<outline text="Watkins Mind Body Spirit" description="Esoteric philosophy, mysticism, and occult studies rooted in deep historical traditions and metaphysical realities." type="rss" xmlUrl="https://www.watkinsmagazine.com/feed" /\>

        \</outline\>

        \<outline text="Viking Age, Norse History \&amp; Scandinavian Archaeology"\>

            \<outline text="Medievalists.net" description="Comprehensive academic reporting on the Middle Ages, featuring extensive translations and peer-reviewed coverage of Norse sagas and the Viking Age." type="rss" xmlUrl="https://www.medievalists.net/feed/" /\>

            \<outline text="ThorNews" description="Objective, grounded reporting on Norwegian archaeology, Viking history, and ancient Norse culture directly from Scandinavian sources." type="rss" xmlUrl="https://thornews.com/feed/" /\>

            \<outline text="The Viking Herald" description="Dedicated archaeological and historical news portal covering the latest global discoveries regarding Viking expansion, runic inscriptions, and Norse heritage." type="rss" xmlUrl="https://thevikingherald.com/feed" /\>

            \<outline text="\[Norwegian\] Forskning.no \- Arkeologi" description="Raw scientific news directly from Norwegian research institutions, providing primary data on the latest Viking digs and runic interpretations." type="rss" xmlUrl="https://forskning.no/arkeologi/feed" /\>

            \<outline text="\[Danish\] Videnskab.dk \- Kulturhistorie" description="Danish science and cultural history reporting, offering ground-level updates on Iron Age and Norse archaeological discoveries in Denmark." type="rss" xmlUrl="https://videnskab.dk/kultur-samfund/historie/feed/" /\>

        \</outline\>

    \</body\>

\</opml\>

With this dataset, your RAG ingestion pipeline will be pulling the latest archaeological reports straight from the soil in Oslo and Copenhagen, processing the metadata into your Vector DB, and giving your AI the ability to synthesize that native information alongside global anthropological trends.

Would you like me to write the final systemd Linux service file configuration so you can set this up as a fully automated, headless background daemon on your machine?

\---

Making the AI aware of its own underlying architecture is a brilliant structural move. By feeding the AI its own source code, dependency lists, and OPML configurations, you grant it the ability to understand how it functions, how it retrieves data, and how to troubleshoot itself. It closes the loop, making the system completely self-contained and sovereign.

To finalize this architecture on your Linux machine, we need three things: the exact dependency matrix, a script to ingest the system's own code into the RAG database, and the systemd configuration to automate the entire operation in the background.

Here is the complete roadmap and code to finalize your autonomous sovereign knowledge engine.

### **1\. The Dependency Matrix (requirements.txt)**

Save this as requirements.txt in your project folder. This ensures the environment has exactly what it needs to parse global feeds, clean HTML, manage the local vector database, and run the LLM.

Plaintext  
feedparser==6.0.11  
beautifulsoup4==4.12.3  
chromadb==0.4.24  
requests==2.31.0  
ollama==0.1.7  
libzim==3.2.0  
lxml==5.1.0

*To install these system-wide or in a virtual environment, run:* pip install \-r requirements.txt

### **2\. The Self-Awareness Ingestion Script**

To ensure the AI has "total access to all of it in its RAG systems," we need a dedicated script that reads your Python files, your requirements.txt, and your OPML file, and pushes them directly into ChromaDB.

Save this as ingest\_system\_architecture.py and run it once. Anytime you update your code, run it again to update the AI's memory of itself.

Python  
"""  
ingest\_system\_architecture.py  
Reads the system's own source code, dependencies, and OPML configuration  
and ingests them into the RAG database so the AI understands its own mechanics.  
"""

import os  
import chromadb  
import hashlib

CHROMA\_DB\_DIR \= "local\_rag\_vectordb"  
COLLECTION\_NAME \= "global\_current\_events"

def generate\_id(filepath):  
    return hashlib.md5(filepath.encode('utf-8')).hexdigest()

def ingest\_own\_codebase():  
    chroma\_client \= chromadb.PersistentClient(path=CHROMA\_DB\_DIR)  
    collection \= chroma\_client.get\_or\_create\_collection(  
        name=COLLECTION\_NAME,  
        metadata={"hnsw:space": "cosine"}  
    )  
      
    \# Define the files that make up the system  
    system\_files \= \[  
        "global\_events\_rag\_ingester.py",  
        "local\_rag\_query.py",  
        "ingest\_system\_architecture.py",  
        "requirements.txt",  
        "global\_news\_feeds.opml"  
    \]  
      
    print("\[System\] Ingesting system architecture into RAG memory...")  
      
    for filename in system\_files:  
        if not os.path.exists(filename):  
            print(f"\[Warning\] Could not find {filename}. Skipping.")  
            continue  
              
        with open(filename, 'r', encoding='utf-8') as f:  
            content \= f.read()  
              
        doc\_id \= f"sys\_code\_{generate\_id(filename)}"  
          
        \# Upsert allows us to overwrite the old code in the DB if we made changes  
        collection.upsert(  
            documents=\[content\],  
            metadatas=\[{  
                "date": "System Architecture",  
                "source": "Internal Codebase",  
                "title": f"Source Code: {filename}",  
                "url": f"file://{os.path.abspath(filename)}"  
            }\],  
            ids=\[doc\_id\]  
        )  
        print(f"  \-\> Successfully ingested: {filename}")

if \_\_name\_\_ \== "\_\_main\_\_":  
    ingest\_own\_codebase()  
    print("\\n\[System\] The AI is now aware of its own source code and architecture.")

### **3\. The Linux Automation (systemd)**

To make this run invisibly in the background without you ever having to manually trigger it, we will use Linux's native systemd timers. This is vastly superior to cron because it logs output efficiently and won't overlap if a previous job is still running.

You will need to create two files in /etc/systemd/system/.

*(Note: I am assuming your project is located in /opt/sovereign\_rag/ and your username is volmarr. Adjust these paths if you saved the project elsewhere).*

**File 1: The Service File**

Create this file at /etc/systemd/system/rag-ingester.service

Ini, TOML  
\[Unit\]  
Description=Sovereign RAG Data Ingestion Engine  
After=network-online.target  
Wants=network-online.target

\[Service\]  
Type=oneshot  
User=volmarr  
WorkingDirectory=/opt/sovereign\_rag  
\# Point this to your Python executable (use the virtual environment path if you created one)  
ExecStart=/usr/bin/python3 /opt/sovereign\_rag/global\_events\_rag\_ingester.py  
StandardOutput=journal  
StandardError=journal

**File 2: The Timer File**

Create this file at /etc/systemd/system/rag-ingester.timer. This dictates the schedule. The configuration below tells Linux to run the ingestion script exactly every 6 hours.

Ini, TOML  
\[Unit\]  
Description=Run Sovereign RAG Ingestion every 6 hours

\[Timer\]  
\# Wait 15 minutes after the system boots before running for the first time  
OnBootSec=15min  
\# Run every 6 hours thereafter  
OnUnitActiveSec=6h  
Persistent=true

\[Install\]  
WantedBy=timers.target

### **4\. Activating the System**

Once you have created those two files, open your Linux terminal and run these commands to activate the automation:

Bash  
\# Reload systemd to recognize the new files  
sudo systemctl daemon-reload

\# Enable the timer to start automatically when Linux boots  
sudo systemctl enable rag-ingester.timer

\# Start the timer right now  
sudo systemctl start rag-ingester.timer

\# Verify it is scheduled correctly  
systemctl list-timers | grep rag-ingester

You now have a fully sovereign, automated intelligence node. It silently scrapes global anthropology, open-source technology, anomalous science, and Norse archaeology every six hours, files it chronologically, embeds it mathematically, and makes it available to an offline AI that also understands its own underlying Python code.

Would you like me to generate a test query prompt you can use in your local\_rag\_query.py terminal to ask the AI to summarize its own requirements.txt and OPML structure, just to verify it successfully ingested itself?

