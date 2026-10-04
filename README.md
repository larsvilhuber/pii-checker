# PII Checker

Version: see [`version.py`](version.py) (`python interface.py --version`).

Replication packages shared alongside published research sometimes contain personally identifiable information (PII) that was never intended for publication. PII Checker helps researchers, data editors, and repositories scan replication packages for direct PII to help mitigate such unintended disclosure before publication.

This is the **local, run-it-yourself version**: a command-line tool that searches research replication packages (data files in a folder or archive) for columns that may contain PII, using an LLM to evaluate each candidate column.

By default, everything runs locally: with Ollama on `localhost`, no data ever leaves your computer. Data only leaves your machine if you deliberately configure a remote Ollama endpoint, or switch providers to Anthropic/OpenAI (see [Requirements](#requirements)).

For a description of what the tool actually checks and how, see [METHODOLOGY.md](METHODOLOGY.md).

A hosted version of this tool (no local setup required) is available for data editors and repositories — see [piichecker.org](https://piichecker.org).

## What it detects

The tool is designed to detect **direct identifiers** (names, emails, phone numbers, precise locations/coordinates, IP addresses). Columns may also be flagged as possible indirect identifiers, but there is no holistic evaluation of the overall risk of reidentification of respondents.

It only searches for PII in tabular data. Documents such as `.pdf` or `.doc`, or multimedia files, are not evaluated. Supported file formats:

- Excel — `.xls`, `.xlsx`
- Plain text tabular data — `.csv`, `.tsv`, `.tab`, `.txt`, `.dat`
- Stata — `.dta`
- R — `.rds`, `.rdata`, `.rda`
- SPSS — `.sav`, `.zsav`, `.por`
- SAS — `.sas7bdat`, `.xpt`
- Matlab — `.mat`
- OpenDocument — `.ods`

Archives are unpacked automatically: `.zip`, `.7z`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, and `.gz` (`.rar` is not supported — extract it manually first).

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Running it](#running-it)
- [Usage](#usage)
- [License](#license)

<h2 id="requirements">Requirements</h2>

- Python 3.10+
- [Ollama](https://ollama.com/) running locally (or reachable over your network) to serve the LLM
- Enough RAM to hold the model you choose — no GPU is required, but one might make evaluation significantly faster

<h2 id="installation">Installation</h2>

**1. Install Ollama and pull a model**

Download and install Ollama from [ollama.com](https://ollama.com/download), then pull the model you plan to use:

```
ollama pull gemma4:26b
```

Make sure Ollama is running (it starts automatically on most installs; otherwise run `ollama serve`). You can confirm it's running and the model was pulled successfully with:

```
ollama list
```

The model you chose (e.g. `gemma4:26b`) should appear in the output.

**2. Get the code**

```
git clone https://github.com/valentadavid/pii-checker.git
cd pii-checker
```

**3. Install Python dependencies**

```
pip install -r requirements.txt
```

[//]: # (Only needed if you plan to use Anthropic or OpenAI instead of Ollama:)

[//]: # ()
[//]: # (```)

[//]: # (pip install -r requirements-optional.txt)

[//]: # (```)

**4. Configure environment variables**

Copy `config.env.example` to `config.env` in the project root and adjust it to reflect your chosen model. 

- `LLM_PROVIDER` — `ollama`, `anthropic`, or `openai`
- `LLM_MODEL` — the exact model tag, e.g. an Ollama model name you've pulled
- `OLLAMA_ENDPOINTS` — comma-separated Ollama endpoint(s); defaults to the local instance
- Ollama is reached over plain HTTP, so don't point it at a remote endpoint over an untrusted network
- Do not use Anthropic or OpenAI for any data that might contain PII, only recommended for testing or benchmarking on synthetic data

<h2 id="running-it">Running it</h2>

**1. Make sure Ollama is running**

Ollama needs to be running before you start the script — start it with `ollama serve` if it isn't already (see [Installation](#installation)).

**2. Run the script**

You just need to run `interface.py` — it's an interactive command-line script, no arguments needed.

- **From a terminal:** `python interface.py [folder] [--many] [--model [NAME]]` — giving the folder runs it as a single package with no prompts (add `--many` for a folder of packages); `--model` alone lists the models on your Ollama endpoint and lets you pick one, `--model NAME` uses that model directly; `--continue` keeps the model loaded in Ollama afterwards for a follow-up run (by default it is unloaded when the script ends, so it doesn't stay resident for other users of the endpoint)
- **From PyCharm (or any IDE):** open the project, then right-click `interface.py` → Run

By default it uses the model from `config.env`. With `--model` (and `LLM_PROVIDER=ollama`) it lists the models pulled on your Ollama endpoint and asks which one to use — press Enter to keep the one in `config.env`, or type a number/name to switch. If you switch, it asks whether to save the choice to `config.env` (permanent) or use it for this session only. It then verifies the setup is actually working (a live test call succeeds) before asking anything else. If that check fails, fix the reported issue (start Ollama, pull the model, fix `config.env`, etc.) and run it again.

<h2 id="usage">Usage</h2>

After the startup check, you're asked to choose a mode:

**1. Single package** — point it at one folder containing a replication package (data files, possibly zipped). It unzips archives, cleans junk files, finds duplicate files, and evaluates every candidate column. Results are saved to `pii_checker_results.xlsx` inside that folder.

**2. Many packages in a folder** — point it at a folder containing multiple package subfolders (e.g. one subfolder per dataset/study). Each subfolder is processed the same way as single-package mode, with its own `pii_checker_results.xlsx`, and results are also rolled up into `pii_checker_overview.xlsx` in the parent folder.

The overview file tracks a `status` per package (`pending`, `running`, `done`, `skip`, or an error state) plus summary counts (files found, duplicates, columns checked, and how many were flagged `direct_pii`/`possible_indirect`/`internal_id`). This makes the batch run **resumable** — if it's interrupted, just run it again and it picks up where it left off (any package left `running` is retried automatically).

To re-run a package that's already finished (`done`, or any error state), manually edit its `status` cell back to `pending` and run the batch again — it'll be picked up on the next pass. To permanently exclude a package instead, set its status to `skip` and, optionally, record why in the `notes` column.

Each `pii_checker_results.xlsx` has up to four sheets:

- **Overview** — the key numbers for a reviewer: what was scanned, how many columns were flagged, and whether anything went wrong.
- **Results** — one row per checked column, with the evaluation, the model's one-sentence reasoning, and the values it was shown, so you can audit *why* it made each call.
- **Issues** — warnings and errors from the run (only present if there were any).
- **Metadata** — the complete record of how the file was produced (tool version, model, timing, archive hashes, token usage).

