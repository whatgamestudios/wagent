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

# Generate an Instagram-ready word card (word + meaning) as a PNG
python -m worcadian_agent.image_card GROWTH "the process of increasing in size, extent, or quantity"
```

### Generating a word card image

`image_card.py` renders a word and its meaning onto a parchment/newspaper-style
graphic card (Pillow only — no AI image generation), sized for Instagram:

```bash
python -m worcadian_agent.image_card ZYTHUM "an ancient Egyptian fermented beverage made from barley" --output-dir output
```

Output is written to `output/<WORD>-<date>.png`, e.g. `output/ZYTHUM-2026-08-18.png`.

Options:

```bash
python -m worcadian_agent.image_card WORD "meaning" --width 1080 --height 1350  # portrait card
python -m worcadian_agent.image_card WORD "meaning" --output path/to/file.png   # explicit output path
python -m worcadian_agent.image_card WORD "meaning" --font-dir /path/to/fonts  # custom regular.ttf/bold.ttf/italic.ttf
python -m worcadian_agent.image_card WORD "meaning" --kicker "CUSTOM KICKER" --footer "custom footer"
```

It looks for Georgia (macOS) or DejaVu Serif (Linux) by default; use `--font-dir`
to point at your own fonts if neither is installed.

### Generating an AI-illustrated image

`generative_image.py` calls Google's Gemini image-generation model (via a
Google AI Studio API key) to generate a genuine AI illustration representing
the word's meaning, rather than compositing a text card:

```bash
python -m worcadian_agent.generative_image ZYTHUM "an ancient Egyptian fermented beverage made from barley"
```

Requires `GOOGLE_API_KEY` set (in `.env` or the environment). Get a free key
from [Google AI Studio](https://aistudio.google.com/apikey), then add it to
your `.env`:

```bash
GOOGLE_API_KEY=your-key-here
```

Output is written to `output/<WORD>-<date>-ai.png`, e.g. `output/ZYTHUM-2026-08-18-ai.png`.

Options:

```bash
python -m worcadian_agent.generative_image WORD "meaning" --aspect-ratio 3:4   # portrait
python -m worcadian_agent.generative_image WORD "meaning" --output path/to/file.png
python -m worcadian_agent.generative_image WORD "meaning" --model gemini-2.5-flash-image
python -m worcadian_agent.generative_image WORD "meaning" --style "flat vector illustration, bold colors"
```

The prompt is built from the word, its meaning, and the `--style` hint, and
explicitly asks the model not to render any text/letters in the image (image
models are unreliable at spelling), so pair the output with a caption in the
Instagram post itself rather than relying on in-image text.
