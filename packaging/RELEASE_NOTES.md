## ATS Simulator, desktop app

A simulator of applicant tracking systems: see how a resume is parsed, screened and ranked, and why. It runs entirely on your computer; resumes are read, analyzed and deleted. It is modeled on documented ATS behavior and does not reproduce or predict any vendor's system.

### Download

| System | File | Open with |
|---|---|---|
| Windows 10 or 11 | `ATS-Simulator-Windows.zip` | Unzip, double-click `ATS-Simulator.exe` |
| macOS, Apple Silicon (M1 or later) | `ATS-Simulator-macOS-AppleSilicon.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| macOS, Intel | `ATS-Simulator-macOS-Intel.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| Linux (x86-64) | `ATS-Simulator-Linux.zip` | Unzip, run `./ATS-Simulator` |

The builds are not signed with a paid developer certificate, so the system warns the first time. On Windows click *More info*, then *Run anyway*. On macOS right-click, choose *Open*, then confirm. Each file is about 340 to 445 MB because it carries Python, every library and the language model; no other install is needed.

The first launch takes about 20 seconds. The app opens in its own window on Windows and macOS and in your browser on Linux. Data, the learned model and a log file live in `~/.ats_sim` (or `%APPDATA%\ats_sim` on Windows).

### New in this version

- **The learned parser has read real resumes.** Its starting model now also learns from 90 public, anonymized real resumes (the CC0 LiveCareer dataset). On 500 other real resumes it labels 89% of lines correctly, up from 79%, with no real loss on unusual designs. Before, it had only ever seen fictional resumes.
- **Two new research experiments, both on real data.** Experiment 9 tests every parser on 2,482 real resumes, labeled automatically from their own web pages: the heading list labels 82% of lines, and only 68% of real section headings are in it ("Highlights", "Accomplishments" and "Additional Information" are the most common misses). Experiment 10 renders the fictional resumes through 54 real third-party designs (JSON Resume themes from npm): the simple parser scores below 0.5 on 40 of them.
- **A new check: "Every letter is read twice"**, for designs that draw text twice for a bold or shadow effect, which a parser reads as "PPrriiyyaa".

### What the app does

- **Resume check:** upload a PDF or Word resume and paste a job description. See the screening rules read from the posting and how your resume meets each one, your score and rank with three scorers, the terms found and missing, what each parser read, and a list of parsing risks, including a visual check that compares the page with the text an ATS extracts. **Download report** saves it all.
- **Learned parser:** a small neural network that labels each line with its section and learns from your corrections in *Teach the model*, on this computer only.
- **Screening, Boolean search and Research:** a recruiter's view of 16 fictional candidates, keyword search, and charts for all ten experiments.

Full methods, results and limitations are in the repository README.
