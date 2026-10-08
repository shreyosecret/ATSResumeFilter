## ATS Simulator, desktop app

A simulator of applicant tracking systems: see how a resume is parsed, screened and ranked, and why. It runs entirely on your computer; resumes are read, analyzed and deleted. It is modeled on documented ATS behavior and does not reproduce or predict any vendor's system.

### Download

| System | File | Open with |
|---|---|---|
| Windows 10 or 11 | `ATS-Simulator-Windows.zip` | Unzip, double-click `ATS-Simulator.exe` |
| macOS, Apple Silicon (M1 or later) | `ATS-Simulator-macOS-AppleSilicon.zip` | Unzip, right-click `ATS Simulator.app`, choose *Open* |
| Linux (x86-64) | `ATS-Simulator-Linux.zip` | Unzip, run `./ATS-Simulator` |

The builds are not signed with a paid developer certificate, so the system warns the first time. On Windows click *More info*, then *Run anyway*. On macOS right-click, choose *Open*, then confirm. Each file is about 300 to 400 MB because it carries Python, every library and the language model; no other install is needed.

The first launch takes about 20 seconds. The app opens in its own window on Windows and macOS and in your browser on Linux. Data, the learned model and a log file live in `~/.ats_sim` (or `%APPDATA%\ats_sim` on Windows).

### In this version

- **A visual check.** The app now reads each page of a PDF the way a person sees it, with an OCR model that runs on your computer, and compares that with the text an ATS extracts. It warns about text on the page that an ATS cannot read (drawn as an image, or a scanned page) and about words that run together in the file's text. It found no false alarms on 60 test resumes.
- **Words no longer run together.** In tightly spaced text the app read "Built a survival model" as "Builtasurvivalmodel", so keyword search missed every word inside. Words now split at a gap relative to the font size, as other PDF readers do.
- **A logo**, in the app, on its icon and on the About page.
- **Research: experiment 8.** OCR against two small vision-language models (Florence-2 and SmolVLM) as page readers. OCR read 99% of words and changed 1%; the vision-language models changed 9% and 18% of the words they returned, which is why the app uses OCR.
- **Wrapped bullets stay whole.** A bullet that runs over two or more lines in a PDF was read as separate lines in the *Teach the model* tab and by the learned parser. The app now joins wrapped lines back into the bullet they belong to, using where each line sits on the page and whether its first word would have fit on the line above. New bullets, lines with right-aligned dates, `Label:` lines and contact details are never joined. Pasted job descriptions get the same treatment, so a requirement like "degree in Computer Science or a / related field" is read as one sentence. The *Extracted text* tab still shows the raw extraction, since that is what an ATS sees.
- **Score your resume against any job.** Copy a job description from a job site and paste it into *Resume check*. The app reads its screening rules (degree level and field, minimum GPA, graduation window, work authorization, visa sponsorship), shows the sentence each rule came from, checks your resume against each one, and scores and ranks the resume against that posting with the three scorers. It lists the required and preferred terms it found and the ones it did not. A field list that allows "a related field" is shown but not used to reject.
- Resume check: parsing risks, what each parser read, knockouts, and percentile ranks. **Download report** saves the whole analysis as a Markdown file.
- Learned parser: a small neural network that labels each line with its section, reads page layout to find headings, and learns from resumes you correct in the *Teach the model* tab. New: its fields refresh as soon as you teach it, and the tab says when it is still loading.
- Research: charts for all eight experiments, including learning from corrections, training on 50 generated formats, and reading page geometry.
- An app icon, and a *Check for updates* link on the About page.

Full methods, results and limitations are in the repository README.
