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

- **Scanned resumes are read with OCR.** When a PDF is only a picture of a page, an ATS without OCR reads nothing. The app says so and now also shows what an ATS that runs OCR would read, in a *With OCR* column of the parser comparison.
- **Export labels.** In *Teach the model*, save a resume's lines and your corrected labels to a file, with your name, email, phone and links replaced by placeholders. Nothing is sent: you choose whether to share it, for example to help test the parser on real resumes.
- **Optional update check.** Turn it on in About and the app tells you when a newer version is out. It is off by default; when on, it asks GitHub for the latest version number and sends nothing else.
- **An Intel Mac build**, alongside Apple Silicon.
- **The learned parser now reads text only.** Experiment 7 was rerun on the current reader (joined wrapped lines, font-relative word gaps). The text-only network matched or beat the version that also used page layout in every test group and on a real resume (0.83 of its lines right, against 0.81), so it is now the default. Page layout is still used to join wrapped lines and in the visual check.
- A slightly smaller download (the OCR image library without a GUI toolkit), and an automated browser test that clicks through the app on every change.

### What the app does

- **Resume check:** upload a PDF or Word resume and paste a job description. See the screening rules read from the posting and how your resume meets each one, your score and rank with three scorers, the terms found and missing, what each parser read, and a list of parsing risks, including a visual check that compares the page with the text an ATS extracts. **Download report** saves it all.
- **Learned parser:** a small neural network that labels each line with its section and learns from your corrections in *Teach the model*, on this computer only.
- **Screening, Boolean search and Research:** a recruiter's view of 16 fictional candidates, keyword search, and charts for all eight experiments.

Full methods, results and limitations are in the repository README.
