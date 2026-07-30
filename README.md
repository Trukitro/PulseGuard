<p align="center">
  <img src="assets/logo.png" alt="PulseGuard" width="400">
</p>

# PulseGuard

A Windows desktop resource watchdog: it watches RAM / CPU / NVIDIA GPU usage, detects sudden **spikes** (not just high totals), tells you which process caused it, and shows it all in a native-feeling desktop window built with real HTML/CSS/JS.

## Installation

**End users:** download the latest installer from [Releases](https://github.com/Trukitro/PulseGuard/releases) and run `PulseGuardSetup.exe`. No Python required.

**Developers:**

```bash
git clone https://github.com/Trukitro/PulseGuard.git
cd PulseGuard/backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Run the backend core standalone in a console (no server, no UI) to see live stats:

```bash
python -m app.console
```

Run the full local server, then open `http://127.0.0.1:8731` in a browser to develop the UI:

```bash
uvicorn app.main:app --reload --port 8731
```

Run the packaged desktop app (once `shell.py` / PyInstaller build exists):

```bash
python -m app.shell
```

## Project structure

```
pulseguard/
├── assets/       # icon, logo
├── backend/      # FastAPI + sampler/detector/snapshot/history (Python)
├── frontend/     # HTML/CSS/JS web components UI
├── installer/    # Inno Setup script
└── .github/      # CI/CD release pipeline
```

See [`PulseGuard-project-plan.md`](PulseGuard-project-plan.md) for the full architecture, API contract, and build-order spec.

## License

[MIT](LICENSE)
