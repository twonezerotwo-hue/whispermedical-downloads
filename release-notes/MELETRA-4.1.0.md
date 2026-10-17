# MELETRA 4.1.0 - Medical Learning & Transcription (Windows x64)

MELETRA turns a lecture recording into an accurate transcript with medical terms checked in context, plus a summary, key concepts, flashcards and questions.
Transcription, medical term correction, PDF reading and text recognition run on your own computer; audio, video, PDF files and pictures never leave it.

## Install (Windows 10 / 11, 64-bit)

Open the download page, choose **Download MELETRA for Windows** and run `MELETRA-Installer-Windows.exe`:
https://twonezerotwo-hue.github.io/whispermedical-downloads/

The small installer program downloads the program and the Whisper Large-v3 speech model from this release, checks the size and SHA-256 of every file against the published
list and refuses anything that does not match, then installs MELETRA. It continues where it stopped if your connection drops. After the installation MELETRA works offline.

| File | What it is |
|---|---|
| `MELETRA-Installer-Windows.exe` | the one-click installer program (about 0.1 MB) |
| `MELETRA-Setup-Windows-x64.exe` | the full MELETRA setup that the installer program downloads and runs (you do not need to download it yourself) |
| `SHA256SUMS.txt` | the SHA-256 of both files above |

Windows may show "Windows protected your PC" because the installer is **not code-signed yet**: choose More info, then Run anyway.

## What is new

* The program is now called **MELETRA** (it was WhisperMedical, and before that Medical Lecture Transcriber), with a new logo and icon.
* One simple workflow on Home: drop a recording anywhere in the window, optionally add the lecture's PDF, choose the Input language (Auto Detect) and the Output language (English), press TRANSCRIBE.
* Ten languages with translation; Recent lectures and a Files archive (rename, search, sort); Study with summary, key concepts, flashcards, questions and Study Mode; keyboard and screen-reader support.

## Your privacy

Nothing is shared unless you switch it on. Sending the text of completed transcripts to MELETRA to help improve transcription quality is **off by default**; you can turn it on in
Settings -> Privacy & Data after you have seen exactly what would be shared, and off again at any time.

## Upgrading

Install MELETRA over WhisperMedical or Medical Lecture Transcriber. The earlier program is replaced; **your lectures, transcripts, Study material, archive, settings and models are kept.**

## Not included

Intel Mac: not available yet (a MELETRA.app is offered only after it has been tested on a real Intel Mac).
