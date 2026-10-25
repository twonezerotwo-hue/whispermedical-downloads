# MELETRA 4.1.2 - Medical Learning & Transcription (Windows x64)

MELETRA turns a lecture recording into an accurate transcript with medical terms checked in context, plus a summary, key concepts, flashcards and questions.
Transcription, medical term correction, translation, PDF reading and text recognition run on your own computer; audio, video, PDF files and pictures never leave it.

## Install or update (Windows 10 / 11, 64-bit)

Open the download page, choose **Download MELETRA for Windows** and run `MELETRA-Installer-Windows.exe`:
https://twonezerotwo-hue.github.io/whispermedical-downloads/

The small installer program downloads the program, the Whisper Large-v3 speech model and (optional, ticked by default) the offline translation pack from this repository, checks the size
and SHA-256 of every file against the published list and refuses anything that does not match, then installs MELETRA. It continues where it stopped if your connection drops. After the
installation MELETRA works offline. Installing over 4.1.1 (or an earlier version) keeps your lectures, transcripts, Study packs, archive, settings, review progress and models.

| File | What it is |
|---|---|
| `MELETRA-Installer-Windows.exe` | the one-click installer program (about 0.1 MB) |
| `MELETRA-Setup-Windows-x64.exe` | the full MELETRA setup that the installer program downloads and runs (you do not need to download it yourself) |
| `SHA256SUMS.txt` | the SHA-256 of both files above |

Windows may show "Windows protected your PC" because the installer is **not code-signed yet**: choose More info, then Run anyway.

**macOS is not part of this release.** A Mac version could not be built and tested (the GitHub account refused to start the macOS build machine: payment / spending limit), so none is offered and
nothing is claimed about one.

## What 4.1.2 fixes

* **Read Transcript, Study and Technical Details found no transcript for lectures that were on disk.** The lecture's record named the folder you had chosen instead of the lecture's own folder. One
  lookup now finds a lecture's files (current and older file names) for the result screen, the reader, Study, translation and Technical Details, and corrects the record.
* **Lectures that were missing from Files, and a lecture shown twice ("Queued") next to the finished one.** Files -> *Repair lecture archive* (and a silent repair at start-up) restores them; it never
  deletes, moves or rewrites a transcript, Study pack or recording.
* **One honest status and honest numbers** everywhere (Completed / Completed - metadata recovered / Transcript not found / Interrupted / Failed / Queued; "Unknown", never an invented 0).
* **Transcripts open inside MELETRA** (search, copy, language tabs, timestamps). Explorer is a small secondary action and no longer opens by itself after a transcription.
* **Translate to another language** works on the saved text: no recording, no speech model, no new job.
* **Sharing completed transcript text with MELETRA is asked once, on the first launch**, as a plain choice (Share / Keep private; closing the question means private). The setting, the checkbox, the Home
  chip and what is sent always agree; *Show what would be shared* lists the exact fields; withdrawing stops everything. Audio, video, PDF files and pictures are never sent.

## What is new in Study

* **MELETRA Automatic Study Engine.** There is no method chooser. MELETRA uses a text model that runs on your computer (Ollama, for example `qwen3:8b`) when one is available and its own offline method
  otherwise. Lecture text is never sent to a cloud service automatically; a cloud provider is possible only under Settings -> Study -> Advanced, after a separate explicit consent. While a transcription
  runs, Study does not use the graphics card; when you start a transcription, cancel Study or close the program, the study model is released.
* **Flashcards and questions are checked before you see them**: a real question (no fill-in-the-blank), an answer that says more than the question, evidence quoted from the lecture and verified against it,
  one defensible best answer with plausible wrong options, no repeated card or question, no "why" or "because" the lecture does not give, no item built on a misheard word. Each item remembers its evidence,
  the moment of the lecture and the engine version.
* **Spaced repetition** (the SM-2 algorithm): *Know* brings a card back after 1 day, then 6, then at growing gaps; *Unsure* grows the gap less; *Don't know* brings it back today. The screen shows when each
  answer brings the card back; **Due today** opens first when cards are due; *Mark difficult* (key **D**) keeps your own list; **Left / Right** move between cards; every review is kept.
* **Your progress survives**: closing and reopening MELETRA, a new version (progress from 4.1.1 is read as it is) and regenerating the material (reworded cards inherit the history of the card they repeat).
* **Study Mode resumes** an unfinished session after a restart. **Learning objectives** (Summary tab) are made from the validated cards and questions, with their sources.

## What was measured before this release

* 2,393 automated tests passed, 0 failed (1 skipped: an optional text-recognition package that is not installed on the build computer; the program reads scans and pictures with Windows text recognition).
* The packaged program (the same build as the setup): a 14-step smoke test with real speech recognition on an NVIDIA GPU (Large-v3, float16) and on the CPU, pause and resume, documents with OCR, media formats,
  restart; the user interface at 1366x768, 1440x900 and 1920x1080 (13 pages each), the accessibility tree and a real Windows drag-and-drop; a profile written by 4.0 is migrated without losing a file; with the
  network watched, no connection to an address outside the computer was seen.
* A real 42-minute lecture (a copy of the developer's profile; the lecture is private): the saved transcript is read, Study material is made by the local model in about 13 minutes (35 items kept of 148 the model
  wrote), two flashcard reviews, a difficult mark and an unfinished Study Mode answer survive a restart, and the saved transcript is translated to Turkish with no recording and no speech model.
* Study quality on three synthetic lectures with `qwen3:8b`: no repeated, trivial or unsupported item, every quoted evidence found in the lecture, every multiple-choice question well-formed (tool and packs in the
  source repository's `docs`). **Reading every one of the 54 items found no wrong medical statement and six weak ones** (loose fit between question and answer, one fact asked twice, weak wrong options).

## Limits, stated plainly

* The quality check looks at words, not meaning: a paraphrase and a small inference look alike to it. Read the flashcards you rely on.
* A spoken lecture with speech-recognition errors gives a short Study pack (35 items from a 42-minute lecture), and without a local text model the offline method writes few questions and no multiple-choice ones.
* Translation is machine translation by a small (418M) offline model: usually understandable, sometimes wrong on rare medical terms. Check medical content against the original.
* A CPU-only computer is much slower than one with an NVIDIA GPU.
* The installer is not code-signed.

## Security

Pillow 13.0.0, pypdf 6.21.2 and filelock 4.2.1 replace versions with published advisories. `pip-audit` of the bundled packages reports no known vulnerability (84 packages); the CUDA build of PyTorch cannot
be audited by `pip-audit` and is reported as an exception, not as clean. The built program contains no GPL-class component (checked on the binaries) and no private material.

## Your privacy

Nothing is shared unless you switch it on. Sending the text of completed transcripts to MELETRA to help improve transcription quality is **off by default** (Settings -> Privacy & Data). Audio, video, PDF files and
pictures are never sent. Translation and Study are local; a cloud Study provider needs its own consent and key.
