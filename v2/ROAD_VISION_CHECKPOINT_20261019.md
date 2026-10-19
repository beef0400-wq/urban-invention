# V2.16 bead region fix

Problem: a complete 22-result bead plate was rejected because same-scale coloured count legends joined the detected component, adding a seventh row. A pair badge and white glyph also reduced one tie cell's centre colour coverage below the threshold.

Change: isolate complete six-row regular regions only when neighbouring rows have a non-grid gap; do not slice larger regular grids. Confirm moderately obscured centres using the same cell's outer colour ring. Preserve gap, ambiguity, minimum-result and manual confirmation checks. Both LINE and web upload share this parser. No membership or analysis-rule changes.

Validation: supplied original screenshot yields exact column-major 22 results (Banker 7, Player 12, Tie 3). Original size and 75% size JPEG quality 95/75/50 all yield the exact sequence. 50% size variants remain rejected, not falsely accepted. Eight regression tests cover plain plates, legends/overlays, holes, obscured cells, multiple boards, minimum results, seven regular rows, big-road-only and invalid input. Python syntax checks pass.

Remaining: verify the deployed LINE round trip by reuploading the original image. This change does not guarantee recognition of all layouts or low-resolution images. No customer screenshot is committed.
