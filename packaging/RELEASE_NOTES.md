## ATS Simulator, desktop app

A simulator of applicant tracking systems: see how a resume is parsed, screened and ranked, and why. It runs entirely on your computer; resumes are read, analyzed and deleted. It is modeled on documented ATS behavior and does not reproduce or predict any vendor's system.

### Download

| System | File | Open with |
|---|---|---|
| Windows 10 or 11 | `ATS-Simulator-Windows.zip` | Unzip, open the `ATS Simulator` folder, double-click `ATS-Simulator.exe` |
| macOS, Apple Silicon (M1 or later) | `ATS-Simulator-macOS-AppleSilicon.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| macOS, Intel | `ATS-Simulator-macOS-Intel.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| Linux (x86-64) | `ATS-Simulator-Linux.zip` | Unzip, run `ATS Simulator/ATS-Simulator` |

The builds are not signed with a paid developer certificate, so the system warns the first time. On Windows click *More info*, then *Run anyway*. On macOS right-click, choose *Open*, then confirm. Everything is included and no other install is needed: Python, every library, the language models, and the comparison parsers in the `engines` folder (keep it next to the program).

The first launch takes about 20 seconds. The app opens in its own window on Windows and macOS and in your browser on Linux. Data, the learned model and a log file live in `~/.ats_sim` (or `%APPDATA%\ats_sim` on Windows).

### New in this version

- **The download now runs every feature.** Until now it left out four: the comparison parsers OpenResume and pyresparser (and their combined vote), the deep skill scan (SkillNer, 31,000 skills), and the real resumes in the ranking pool, so a percentile rank compared you with 16 fictional people. All four are now included: the pool has 252 resumes, 236 of them real.
- OpenResume (AGPL-3.0) and pyresparser (GPL-3.0) ship as separate programs in an `engines` folder beside the app, with their licenses and source links in `engines/THIRD_PARTY.md`.
- Every build is now checked in CI by running one full analysis with every feature on; a build missing any feature is not released.

### What the app does

- **Resume check:** upload a PDF or Word resume and paste a job description. See the screening rules read from the posting and how your resume meets each one, your score and rank with three scorers, the terms found and missing, what each parser read, and a list of parsing risks, including a visual check that compares the page with the text an ATS extracts. **Download report** saves it all.
- **Learned parser:** a small neural network that labels each line with its section and learns from your corrections in *Teach the model*, on this computer only.
- **Screening, Boolean search and Research:** a recruiter's view of 16 fictional candidates, keyword search, and charts for all ten experiments.

Full methods, results and limitations are in the repository README.
