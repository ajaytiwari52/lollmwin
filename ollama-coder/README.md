# Ollama Coder

A terminal coding assistant that runs a local Ollama model against the current project. The app has no runtime Python dependencies. You can run it with Python or build a standalone Windows executable.

## System requirements

### To run from Python

- Windows 10 or 11 (64-bit) for the instructions below.
- Python 3.10 or newer, available as the `py` launcher or `python`.
- Ollama for Windows installed and running.
- A local Ollama model that supports tool calls. The default is `qwen3:8b`.

### To run the built executable

- Windows 10 or 11 (64-bit), on the same architecture used to build the executable.
- Ollama installed and running, plus the selected model downloaded locally.
- Python is **not** required on the machine that runs the executable.

The executable bundles the Coder app and its Python runtime, **not Ollama or the model**. Ollama serves its local API at `http://localhost:11434` by default. Internet access is needed to download Ollama/models and, if requested, to connect to GitHub; normal model requests go to the local Ollama server.

### Hardware and disk

Requirements depend on the Ollama model. As a practical starting point, use a Windows computer with at least 16 GB of system RAM for `qwen3:8b`. Keep several gigabytes free for the model and additional disk space for its download and Ollama cache. The model is downloaded separately and is not included in this repository or executable. Larger models need more memory and disk space. Ollama can use supported GPU acceleration when available; a compatible GPU is optional.

On older or CPU-only computers, `qwen3:8b` can take several minutes to answer coding requests. If it is too slow, try a smaller tool-calling model such as `qwen3:4b`:

```powershell
ollama pull qwen3:4b
ollama-coder --model qwen3:4b
```

The CLI reports progress while waiting for Ollama and streams response text as it becomes available. Use Ctrl+C to interrupt a slow request.

Check that Ollama is installed, running, and has the model:

```powershell
ollama --version
ollama list
ollama pull qwen3:8b
```

If you use another tool-calling model, specify it with `--model`.

## Clone the repository

```powershell
git clone https://github.com/ajaytiwari52/lollmwin.git
cd lollmwin\ollama-coder
```

## Run from Python

Install for the current Windows user:

```powershell
py -m pip install --user .
```

Open a new terminal and run `ollama-coder`. If Windows cannot find the command, add the Python user Scripts directory to your user `PATH`. Get the base directory with:

```powershell
py -m site --user-base
```

Append `\Scripts` to that path, add it through **Windows Settings > System > About > Advanced system settings > Environment Variables**, then open a new terminal. Alternatively, run the installed `ollama-coder.exe` directly from that Scripts directory.

To uninstall the Python package:

```powershell
py -m pip uninstall local-ollama-coder
```

## Build a standalone Windows executable

Build on Windows for the same architecture as the target computer. From the `ollama-coder` directory, create an isolated build environment, install the app's optional build dependency, and create the executable:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install --upgrade pip
py -m pip install ".[build]"
py -m PyInstaller --clean --noconfirm --onefile --console --name ollama-coder --paths src src\ollama_coder\cli.py
```

The executable is created at `dist\ollama-coder.exe`. Copy that file to a directory on `PATH` or invoke it by its full path. The target computer still needs Ollama running and the selected model pulled:

```powershell
ollama pull qwen3:8b
.\dist\ollama-coder.exe --help
```

Do not distribute the contents of `.venv`, `build`, or PyInstaller's temporary files. The single executable in `dist` is the app bundle; the Ollama model remains a separate install/download. The executable may be noticeably larger than the Python source because it includes a Python runtime.

## Use

Open a terminal in the project you want to work on, then run:

```powershell
ollama-coder
ollama-coder "Find and fix the failing test"
ollama-coder --model qwen3:8b --workspace C:\path\to\project
```

Or replace `ollama-coder` with the path to `ollama-coder.exe`.

The assistant can list and read project files, search text, propose file changes, and run commands. It omits common secret files and `.git`. It shows a progress message while Ollama loads the model or generates its first response, then streams response text as it is generated. Press Ctrl+C to interrupt a slow or unwanted response. It displays a diff and asks before every file write, and displays each shell command and asks before running it. Declining an approval leaves the file or command unchanged. Shell commands run in the selected project directory. Type `/exit` or press Ctrl+C to leave.

The program never reads or prints saved Git credentials. Ask it to commit or push only when you intend to do so; it should first review the changes and ask for any missing branch or commit details. Review every proposed command and change before approving.

Options:

```powershell
ollama-coder --help
ollama-coder --host http://localhost:11434 --model qwen3:8b
```
