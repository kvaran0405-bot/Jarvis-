# Turning JARVIS into a product

JARVIS can be rebranded and handed to other people. What's built in:

- **Rebrand:** set `JARVIS_BRAND_NAME` and `JARVIS_BRAND_COLOR` in `.env`. The dashboard title and header follow.
- **Setup for a new owner:** they copy `profile.example.md` to `profile.md` (and `business.example.md` to
  `business.md`), run `start.bat`, then say "first contact" for the getting-to-know-you interview.
- **Backups and moving laptops:** `python -m jarvis backup` (add `--with-settings` to include `.env`) and
  `python -m jarvis restore <zip>`. The dashboard has a Download backup button (without passwords).

Before charging anyone money, sort these out (they're business and legal decisions, not code):

1. **Name and look.** "JARVIS" and the Iron Man style belong to Marvel/Disney. Use your own product name, logo
   and wording.
2. **The AI brains.** Each buyer needs their own AI account (their own Claude plan or Anthropic API key, or a Gemini
   key). Check the providers' terms for reselling or bundling access.
3. **Voices.** VoiceStudio's default voice model is licensed for non-commercial use only. Microsoft Edge's online
   voices and ElevenLabs have their own terms. Pick voices licensed for commercial use.
4. **Third-party pieces.** three.js (MIT), body-muscles outlines (Apache-2.0, keep `web/vendor/body-muscles-*`),
   MediaPipe (Apache-2.0), faster-whisper (MIT). Keep their licence files with the product.
5. **Privacy.** Buyers' data stays on their own laptop. Write a short privacy note saying so, and keep the
   banking block in place.
