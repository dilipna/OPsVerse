# Self-hosted typography

Space Grotesk, IBM Plex Sans and IBM Plex Mono are distributed with their adjacent
SIL Open Font License files. No system-font installation or runtime font service.

Original TTFs were retrieved from the official Google Fonts repository:

- Space Grotesk: `00a38a53f92aef923b9353f40128e8f4552ddae4`, `ofl/spacegrotesk`.
- IBM Plex Sans: `0b58fb370093f9a9f4ff785d94405710b79de67c`, `ofl/ibmplexsans`.
- IBM Plex Mono: `01d5d9f05246fb7090a8403b81257535cb1a088b`, `ofl/ibmplexmono`.

WOFF2 files are format conversions of those retained originals, using fontTools
with Brotli. No glyph or family-name changes. CSS serves the WOFF2 variants;
release identity includes their raw SHA256 hashes and the retained licenses.
