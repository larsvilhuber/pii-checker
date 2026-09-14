# interface.py
# Interactive wrapper for main.py.
#
# Asks the user whether they want to evaluate a single package or many
# packages inside a folder. A single package is run directly via
# run_package(); many packages are delegated to run_folder(), which
# auto-discovers package subfolders and maintains a resumable overview/
# status file (pii_results_overview.xlsx) in that folder.
# Each package gets its own pii_check.xlsx saved inside its own folder.
#
# Command line:
#   python interface.py [folder] [--model [NAME]]
# folder        runs that single package with no prompts (use --many for a
#               folder of packages)
# --model       shows a chooser of models pulled on the Ollama endpoint
# --model NAME  uses NAME without prompting
# Without --model the LLM_MODEL from config.env is used.

import argparse
import os
import sys

from main import _check_dependencies, run_package, run_folder, logger, _rmtree_retrying
from llm_client import (
    DEFAULT_PROVIDER, DEFAULT_MODEL, OLLAMA_ENDPOINTS,
    check_ollama_reachable, list_ollama_models, save_model_to_config,
)


_CHOOSE = object()  # sentinel: --model given without a name


def _parse_model_choice(answer, models, current):
    """Turns a menu answer (1-based number, exact model name, or empty for the
    current model) into a model name. Returns None if the answer is not valid."""
    answer = answer.strip()
    if not answer:
        return current
    if answer.isdigit():
        idx = int(answer) - 1
        return models[idx] if 0 <= idx < len(models) else None
    return answer if answer in models else None


def _ask_model():
    """Lists the models pulled on the Ollama endpoint and lets the user pick one.
    Returns the chosen model; offers to make a non-default choice permanent in
    config.env. Exits if Ollama is unreachable or has no models."""
    if not check_ollama_reachable():
        logger.error("Could not reach Ollama — check OLLAMA_ENDPOINTS/OLLAMA_API_KEY and try again")
        sys.exit(1)

    models = list_ollama_models()
    if not models:
        logger.error("No models found on %s — pull one with 'ollama pull <model>' and try again", OLLAMA_ENDPOINTS[0])
        sys.exit(1)

    current = DEFAULT_MODEL if DEFAULT_MODEL in models else None
    print(f"\nModels available on {OLLAMA_ENDPOINTS[0]}:")
    for i, m in enumerate(models, start=1):
        print(f"  {i}. {m}{'  (current)' if m == current else ''}")
    if current is None:
        print(f"Configured model '{DEFAULT_MODEL}' is not pulled on this endpoint — pick one from the list.")

    prompt = "Model [Enter = current]: " if current else "Model: "
    while True:
        chosen = _parse_model_choice(input(prompt), models, current)
        if chosen:
            break
        print("Please enter a number from the list or an exact model name.")

    if chosen != DEFAULT_MODEL:
        answer = input(f"Save '{chosen}' to config.env as the default? [y/N]: ").strip().lower()
        if answer == 'y':
            save_model_to_config(chosen)
            logger.info("LLM_MODEL=%s written to config.env", chosen)
        else:
            logger.info("Using '%s' for this session only", chosen)
    return chosen


def _ask_mode():
    while True:
        answer = input("Evaluate (1) a single package or (2) many packages in a folder? [1/2]: ").strip()
        if answer in ('1', '2'):
            return answer
        print("Please enter 1 or 2.")


def _ask_folder():
    while True:
        folder = input("Folder path: ").strip().strip('"')
        if os.path.isdir(folder):
            return folder
        print(f"Not a valid folder: {folder}")


def _resolve_folder(folder):
    """Validates a folder given on the command line; exits if it is not a directory."""
    folder = os.path.abspath(os.path.expanduser(folder.strip().strip('"')))
    if not os.path.isdir(folder):
        logger.error("Not a valid folder: %s", folder)
        sys.exit(1)
    return folder


def main():
    parser = argparse.ArgumentParser(description="Interactive PII check of one package or a folder of packages.")
    parser.add_argument("folder", nargs="?", help="package folder to check (prompted for if omitted)")
    parser.add_argument("--many", action="store_true", help="treat FOLDER as a folder of packages instead of a single package")
    parser.add_argument("--model", nargs="?", const=_CHOOSE, default=None, metavar="NAME",
                        help="Ollama model to use; with no NAME, pick from the models on the endpoint. "
                             "Default: LLM_MODEL from config.env")
    args = parser.parse_args()
    if args.folder is None and isinstance(args.model, str) and os.path.isdir(os.path.expanduser(args.model)):
        # "interface.py --model /path" — argparse took the folder as the model name
        args.folder, args.model = args.model, _CHOOSE
    folder = _resolve_folder(args.folder) if args.folder else None  # fail fast on a bad path

    if args.model == _CHOOSE and DEFAULT_PROVIDER == 'ollama':
        model = _ask_model()
    elif args.model and args.model != _CHOOSE:
        model = args.model
    else:
        model = DEFAULT_MODEL
    _check_dependencies(model=model)

    if folder is None:
        mode = _ask_mode()
        folder = _ask_folder()
    else:
        mode = '2' if args.many else '1'

    if mode == '1':
        packages = [folder]
        for i, package_folder in enumerate(packages, start=1):
            name = os.path.basename(os.path.normpath(package_folder))
            output_path = os.path.join(package_folder, "pii_check.xlsx")
            temp_base = os.path.join(package_folder, "temp_pii_scan")
            os.makedirs(temp_base, exist_ok=True)

            logger.info("[%d/%d] Starting package: %s", i, len(packages), name)
            try:
                run_package(
                    package_folder,
                    output_path,
                    temp_base=temp_base,
                    model=model,
                )
            except Exception as e:
                logger.error("Package failed: %s — %s", name, e, exc_info=True)
            finally:
                _rmtree_retrying(temp_base)  # run_package already cleans up its own subdir; this catches any leftovers
            logger.info("[%d/%d] Finished package: %s", i, len(packages), name)
    else:
        run_folder(folder, model=model)


if __name__ == "__main__":
    main()