# Worcadian Daily Press Release Agent

Generates a daily newspaper-style press release about the [Worcadian](https://whatgamestudios.com/worcadian/) 
word puzzle: it fetches today's seed word and best submissions from the live game server, scores how obscure
the words played are, checks whether players independently found the same words, and uses an LLM
(local Ollama or remote Claude) to write a ~500-word summary.

For how it's built: see [DESIGN.md](DESIGN.md).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # then edit .env for your chosen LLM provider
```

## Running it

Generate today's press release (defaults to the server's current game day, and to a local Ollama model using gemma4:31b):

```bash
python -m worcadian_agent.agent
```

Options:

```bash
python -m worcadian_agent.agent --day 120                        # report on a specific game day
python -m worcadian_agent.agent --provider anthropic              # use remote Claude instead of Ollama
python -m worcadian_agent.agent --provider ollama --model gemma4:31b  # pick a specific Ollama model
python -m worcadian_agent.agent --output-dir output               # where the .txt file is written
```

Output is written to `output/<game_day>-<date>.txt`, e.g. `output/120-2026-07-28.txt`.

### Using Ollama

Requires a local [Ollama](https://ollama.com) server running with a pulled model:


```bash
ollama pull gemma4:31b
python -m worcadian_agent.agent
```

or 

```bash
ollama pull llama3.1
python -m worcadian_agent.agent --provider ollama --model llama3.1
```

or 

```bash
ollama pull mistral 
python -m worcadian_agent.agent --provider ollama --model mistral 
```

After use, you may wish to remove the model from computer memory:

```bash
ollama ps
ollama stop gemma4:31b
```

### Using Claude

Requires `ANTHROPIC_API_KEY` set (in `.env` or the environment):

```bash
python -m worcadian_agent.agent --provider anthropic
```

## Other scripts

Two of the pipeline's building blocks also run standalone:

```bash
# Fetch today's seed word + best submissions + words used, printed as JSON
python -m worcadian_agent.fetch_today [--day N]

# Score how obscure one or more words are
python -m worcadian_agent.word_obscurity GROWTH FLOCKY ZYTHUM

# Calibrate the obscurity thresholds against the full game word list
python -m worcadian_agent.word_obscurity --calibrate
```
