# MELETRA 4.1.1 - Medical Learning & Transcription (Windows x64)

MELETRA turns a lecture recording into an accurate transcript with medical terms checked in context, plus a summary, key concepts, flashcards and questions.
Transcription, medical term correction, translation, PDF reading and text recognition run on your own computer; audio, video, PDF files and pictures never leave it.

## Install or update (Windows 10 / 11, 64-bit)

Open the download page, choose **Download MELETRA for Windows** and run `MELETRA-Installer-Windows.exe`:
https://twonezerotwo-hue.github.io/whispermedical-downloads/

The small installer program downloads the program, the Whisper Large-v3 speech model and (optional, ticked by default) the offline translation pack from this repository, checks the size
and SHA-256 of every file against the published list and refuses anything that does not match, then installs MELETRA. It continues where it stopped if your connection drops. After the
installation MELETRA works offline. Installing over 4.1.0 (or an earlier version) keeps your lectures, transcripts, Study packs, archive, settings and models.

| File | What it is |
|---|---|
| `MELETRA-Installer-Windows.exe` | the one-click installer program (about 0.1 MB) |
| `MELETRA-Setup-Windows-x64.exe` | the full MELETRA setup that the installer program downloads and runs (you do not need to download it yourself) |
| `SHA256SUMS.txt` | the SHA-256 of both files above |

The offline translation pack is a separate release, `translation-m2m100-v1` (Meta M2M100 418M, MIT licence, about 0.5 GB); the installer program fetches it for you.

Windows may show "Windows protected your PC" because the installer is **not code-signed yet**: choose More info, then Run anyway.

## What 4.1.1 fixes

* **A recording that changes language no longer loses the languages that were not "the" language.** A Korean + Hindi + English video used to come out as English only. Auto Detect now follows
  the language through the recording, decodes each stretch in its own language and keeps every recognised language, tagged per segment. Choosing an Input Language yourself works as before.
* **Speech is counted on the audio, not on the voice filter.** Loud stretches without words, and very quiet speech, are looked for and read again; what cannot be read is reported - never invented.
* **"Translate to another language" no longer asks for a new upload.** The result screen translates the **saved** transcript (no file, no new job, no speech model), from Recent Lectures, Files, after
  a restart and after the recording was deleted. Each translation is saved as a tab; asking again opens it at once; a mixed-language lecture is translated segment by segment.
* New: the **saved source transcript** (`source_transcript.json`) that every translation starts from and never overwrites.

## Limits, stated plainly

* Singing over loud music: Whisper writes whatever language it is told to expect, so sung lyrics are often misread; MELETRA marks them uncertain and rejects filler, but cannot name the language of
  singing reliably. On a real 12-minute song compilation it kept Hindi and English lines and found no Korean.
* A language that changes every few seconds or inside one sentence is not resolved reliably.
* Translation is machine translation by a small (418M) offline model: usually understandable, sometimes wrong on rare medical terms. Check medical content against the original.
* A CPU-only computer is much slower than one with an NVIDIA GPU.


## Your privacy

Nothing is shared unless you switch it on. Sending the text of completed transcripts to MELETRA to help improve transcription quality is **off by default** (Settings -> Privacy & Data). Audio, video,
PDF files and pictures are never sent. Translation is local and needs no internet once the pack is installed.
