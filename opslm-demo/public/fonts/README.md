# Self-hosted typography

Current selected theme uses Plus Jakarta Sans, Inter and IBM Plex Mono.
Earlier font assets are retained for historical release provenance, not requested
by the current theme. The current additions come from official Google Fonts:

- Plus Jakarta Sans: `8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5`, `ofl/plusjakartasans`.
- Inter: `0b58fb370093f9a9f4ff785d94405710b79de67c`, `ofl/inter`.

Adjacent original TTFs and OFL files are retained; WOFF2 is a format conversion only.

Space Grotesk, IBM Plex Sans and IBM Plex Mono are distributed with their adjacent
SIL Open Font License files. No system-font installation or runtime font service.

Original TTFs were retrieved from the official Google Fonts repository:

- Space Grotesk: `00a38a53f92aef923b9353f40128e8f4552ddae4`, `ofl/spacegrotesk`.
- IBM Plex Sans: `0b58fb370093f9a9f4ff785d94405710b79de67c`, `ofl/ibmplexsans`.
- IBM Plex Mono: `01d5d9f05246fb7090a8403b81257535cb1a088b`, `ofl/ibmplexmono`.

WOFF2 files are format conversions of those retained originals, using fontTools
with Brotli. No glyph or family-name changes. CSS serves the WOFF2 variants;
release identity includes their raw SHA256 hashes and the retained licenses.
