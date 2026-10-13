# Ollama Coder

A local terminal coding assistant for working in a project, powered by an Ollama model running on your computer. This repository focuses on the standalone coding agent: it can inspect project files, propose code changes, run approved commands and help you commit and push your work.

## What it does

- Uses a locally installed Ollama model; the default is `qwen3:8b`.
- Works from the terminal in any project directory.
- Shows a proposed diff and asks before writing files.
- Shows each shell command and asks before running it.
- Can help with Git commit and push workflows when requested. Review and approve Git operations; GitHub credentials are managed by Git/Git Credential Manager and must never be pasted into the agent.

The agent executable does not include Ollama or the model. Install Ollama and download a tool-calling model separately.

## Quick start on Windows

1. Install and start [Ollama](https://ollama.com/download).
2. Download the default model:

   ```powershell
   ollama pull qwen3:8b
   ```

3. Clone this repository and enter the app directory:

   ```powershell
   git clone https://github.com/ajaytiwari52/lollmwin.git
   cd lollmwin\ollama-coder
   ```

4. Install the terminal command for your current user:

   ```powershell
   py -m pip install --user .
   ```

5. Open a terminal in a project and start the agent:

   ```powershell
   ollama-coder
   ```

   If Windows cannot find the command, add your Python user `Scripts` directory to `PATH` and open a new terminal.

## Build a standalone executable

From `lollmwin\ollama-coder`, build a Windows executable with:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install ".[build]"
py -m PyInstaller --clean --noconfirm --onefile --console --name ollama-coder --paths src src\ollama_coder\cli.py
```

The executable is written to `ollama-coder\dist\ollama-coder.exe`. Python is not needed to run the built executable, but Ollama must be installed, running, and have the model downloaded.

For system requirements, installation alternatives, usage options, and more detailed build instructions, see the [Ollama Coder README](ollama-coder/README.md).
