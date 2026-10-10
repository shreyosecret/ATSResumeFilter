## ATS Simulator, desktop app

A simulator of applicant tracking systems: see how a resume is parsed, screened and ranked, and why. It runs entirely on your computer; resumes are read, analyzed and deleted. It is modeled on documented ATS behavior and does not reproduce or predict any vendor's system.

### Download

| System | File | Open with |
|---|---|---|
| Windows 10 or 11 | `ATS-Simulator-Windows.zip` | Unzip, open the `ATS Simulator` folder, double-click `ATS-Simulator.exe` |
| macOS, Apple Silicon (M1 or later) | `ATS-Simulator-macOS-AppleSilicon.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| macOS, Intel | `ATS-Simulator-macOS-Intel.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| Linux (x86-64) | `ATS-Simulator-Linux.zip` | Unzip, run `ATS Simulator/ATS-Simulator` |

The builds are not signed with a paid developer certificate, so the system warns the first time. On Windows click *More info*, then *Run anyway*. On macOS right-click, choose *Open*, then confirm. Everything is included and no other install is needed: Python, every library, the language models, and the comparison parsers in the `engines` folder. On Windows and Linux keep the `ATS Simulator` folder together: the program needs the `_internal` and `engines` folders beside it.

The window opens in a few seconds and the models finish loading about 10 seconds later; the very first launch is slower. The app opens in its own window on Windows and macOS and in your browser on Linux. Data, the learned model and a log file live in `~/.ats_sim` (or `%APPDATA%\ats_sim` on Windows).

### New in this version

- **Starts faster on Windows and Linux.** The program now ships as a folder instead of one packed file, which had to unpack about 500 MB into a temporary folder on every launch. On Linux the window can open after 2 seconds instead of 9, and the app is fully ready after 11 seconds instead of 18. The macOS app was already built this way.
- From 1.7.0: the download runs every feature, including the comparison parsers OpenResume (AGPL-3.0) and pyresparser (GPL-3.0) in the `engines` folder (licenses and source links in `engines/THIRD_PARTY.md`), the deep skill scan (SkillNer), and a ranking pool of 252 resumes, 236 of them real. Every build is checked in CI by one full analysis with every feature on.

### What the app does

- **Resume check:** upload a PDF or Word resume and paste a job description. See the screening rules read from the posting and how your resume meets each one, your score and rank with three scorers, the terms found and missing, what each parser read, and a list of parsing risks, including a visual check that compares the page with the text an ATS extracts. **Download report** saves it all.
- **Learned parser:** a small neural network that labels each line with its section and learns from your corrections in *Teach the model*, on this computer only.
- **Screening, Boolean search and Research:** a recruiter's view of 16 fictional candidates, keyword search, and charts for all ten experiments.

Full methods, results and limitations are in the repository README.
